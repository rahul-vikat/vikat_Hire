from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import JSONResponse
from langgraph.types import Command
from pydantic import ValidationError

from vikat_hire.app.dependencies import (
    ApplicationDependencyError,
    ScreeningAPIResponse,
    ScreeningGraphPort,
    ScreeningSubmission,
    build_initial_screening_state,
    provide_screening_graph,
    report_from_graph_values,
)
from vikat_hire.collection.resume_extractor import extract_resume_text
from vikat_hire.contracts.common import InputKind, SourceType, WorkflowStatus, new_id
from vikat_hire.contracts.inputs import DocumentInput, ExternalSourceInput, ScreeningInput
from vikat_hire.normalization.document import extract_document_text
from vikat_hire.orchestration.graph import invoke_screening_graph
from vikat_hire.orchestration.interrupts import InputInterruptionError, InputResume
from vikat_hire.orchestration.state import from_orchestration_state

logger = logging.getLogger(__name__)


class RequestSizeLimitMiddleware:
    """Reject oversized request bodies without truncating or parsing them."""

    def __init__(self, app, *, max_bytes: int | Callable[[], int]) -> None:
        if not callable(max_bytes) and max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self.max_bytes() if callable(self.max_bytes) else self.max_bytes
        if max_bytes <= 0:
            raise RuntimeError("configured request size limit must be greater than zero")

        content_length = next(
            (
                value.decode("latin-1")
                for key, value in scope.get("headers", ())
                if key.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > max_bytes:
                    await _send_body_too_large(scope, receive, send)
                    return
            except ValueError:
                await JSONResponse(
                    {"detail": "invalid Content-Length"},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )(scope, receive, send)
                return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > max_bytes:
                await _send_body_too_large(scope, receive, send)
                return
            more_body = message.get("more_body", False)

        sent = False

        async def replay_body():
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay_body, send)


async def _send_body_too_large(scope, receive, send) -> None:
    await JSONResponse(
        {"detail": "request body exceeds configured size limit"},
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    )(scope, receive, send)


def _thread_config(screening_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": screening_id}}


def _snapshot_values(graph: ScreeningGraphPort, screening_id: str) -> Mapping[str, Any] | None:
    snapshot = graph.get_state(_thread_config(screening_id))
    values = getattr(snapshot, "values", None)
    if not isinstance(values, Mapping) or not values:
        return None
    return values


def _response_status(result: ScreeningAPIResponse) -> int:
    if result.interruption is not None:
        return status.HTTP_202_ACCEPTED
    return status.HTTP_200_OK


def _document_from_upload(
    upload: UploadFile,
    *,
    kind: InputKind,
    input_id: str | None = None,
) -> tuple[DocumentInput, bytes]:
    content = upload.file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="uploaded file is empty"
        )
    safe_filename = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not safe_filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uploaded file must have a filename",
        )
    document_id = input_id or new_id()
    document = DocumentInput(
        input_id=document_id,
        kind=kind,
        filename=safe_filename,
        media_type=upload.content_type or "application/octet-stream",
        content_hash=sha256(content).hexdigest(),
        storage_ref=f"upload:{document_id}",
    )
    return document, content


def _provenance_for_document(
    state, document: DocumentInput, source_type: SourceType
) -> tuple[str, ...]:
    refs = tuple(
        item.provenance_id
        for item in state.provenances
        if item.source_type is source_type and item.source_ref == document.input_id
    )
    if len(refs) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"screening checkpoint has invalid {document.kind.value} provenance",
        )
    return refs


def _start_screening(
    *,
    screening_input: ScreeningInput,
    jd_content: bytes | None,
    resume_content: bytes | None,
    response: Response,
    screening_graph: ScreeningGraphPort,
    app: FastAPI,
) -> ScreeningAPIResponse:
    screening_id = screening_input.screening_id
    registry = getattr(app.state, "screening_id_registry", None)
    reserved = False
    if registry is not None:
        if not registry.reserve(screening_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="screening_id already exists",
            )
        reserved = True
        if _snapshot_values(screening_graph, screening_id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="screening_id already exists",
            )
    elif _snapshot_values(screening_graph, screening_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="screening_id already exists",
        )

    try:
        state = build_initial_screening_state(screening_input)
        uploaded_hashes = {}
        if jd_content is not None:
            uploaded_hashes[(SourceType.JD_FILE, screening_input.jd.input_id)] = sha256(
                jd_content
            ).hexdigest()
        if resume_content is not None:
            uploaded_hashes[(SourceType.RESUME_FILE, screening_input.resume.input_id)] = sha256(
                resume_content
            ).hexdigest()
        if uploaded_hashes:
            state = state.model_copy(
                update={
                    "provenances": tuple(
                        provenance.model_copy(
                            update={
                                "content_hash": uploaded_hashes[
                                    (
                                        provenance.source_type,
                                        provenance.source_ref,
                                    )
                                ]
                            }
                        )
                        if (provenance.source_type, provenance.source_ref) in uploaded_hashes
                        else provenance
                        for provenance in state.provenances
                    )
                }
            )
        output = invoke_screening_graph(
            screening_graph,
            state,
            jd_content=jd_content,
            resume_content=resume_content,
            config=_thread_config(screening_id),
        )
        result = report_from_graph_values(output)
    except (ApplicationDependencyError, InputInterruptionError) as exc:
        if reserved and _snapshot_values(screening_graph, screening_id) is None:
            registry.release_if_unstarted(screening_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception:
        if reserved and _snapshot_values(screening_graph, screening_id) is None:
            registry.release_if_unstarted(screening_id)
        raise
    response.status_code = _response_status(result)
    return result


def _resume_graph(
    *,
    screening_id: str,
    payload: InputResume,
    response: Response,
    screening_graph: ScreeningGraphPort,
) -> ScreeningAPIResponse:
    if payload.screening_input.screening_id != screening_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="resume screening_id does not match requested screening",
        )
    try:
        output = screening_graph.invoke(
            Command(resume=payload.model_dump(mode="json")),
            config=_thread_config(screening_id),
        )
        result = report_from_graph_values(output)
    except InputInterruptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    response.status_code = _response_status(result)
    return result


def create_app(
    *,
    graph: ScreeningGraphPort | None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
    title: str = "VikatHire API",
    max_request_bytes: int | Callable[[], int] = 20 * 1024 * 1024,
) -> FastAPI:
    """Create the HTTP boundary around an explicitly injected screening graph."""
    if graph is None and lifespan is None:
        raise ApplicationDependencyError("graph or a composition lifespan is required")
    if graph is not None and (
        not callable(getattr(graph, "invoke", None))
        or not callable(getattr(graph, "get_state", None))
    ):
        raise ApplicationDependencyError("graph must provide invoke() and get_state()")
    if graph is not None and getattr(graph, "checkpointer", None) is None:
        raise ApplicationDependencyError(
            "graph must be compiled with an injected LangGraph checkpointer"
        )

    app = FastAPI(title=title, lifespan=lifespan)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=max_request_bytes)
    if graph is not None:
        app.state.screening_graph = graph

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readiness")
    def readiness() -> dict[str, str]:
        screening_graph = getattr(app.state, "screening_graph", None)
        if screening_graph is None or getattr(screening_graph, "checkpointer", None) is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="screening service is not ready",
            )
        registry = getattr(app.state, "screening_id_registry", None)
        if registry is not None:
            try:
                registry.ping()
            except Exception as exc:
                logger.warning(
                    "Readiness database check failed (%s)",
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="screening service is not ready",
                ) from exc
        return {"status": "ready"}

    @app.post(
        "/screenings",
        response_model=ScreeningAPIResponse,
        status_code=status.HTTP_200_OK,
    )
    def create_screening(
        submission: ScreeningSubmission,
        response: Response,
        screening_graph: ScreeningGraphPort = Depends(provide_screening_graph),
    ) -> ScreeningAPIResponse:
        return _start_screening(
            screening_input=submission.screening_input,
            jd_content=submission.jd_content,
            resume_content=submission.resume_content,
            response=response,
            screening_graph=screening_graph,
            app=app,
        )

    @app.post(
        "/screenings/upload",
        response_model=ScreeningAPIResponse,
    )
    def create_screening_from_upload(
        response: Response,
        screening_id: str = Form(...),
        jd_file: UploadFile = File(...),
        resume_file: UploadFile = File(...),
        linkedin_url: str | None = Form(None),
        github_url: str | None = Form(None),
        portfolio_url: str | None = Form(None),
        linkedin_authorized: bool = Form(False),
        github_authorized: bool = Form(False),
        portfolio_authorized: bool = Form(False),
        screening_graph: ScreeningGraphPort = Depends(provide_screening_graph),
    ) -> ScreeningAPIResponse:
        jd_document, jd_content = _document_from_upload(jd_file, kind=InputKind.JD)
        resume_document, resume_content = _document_from_upload(
            resume_file,
            kind=InputKind.RESUME,
        )
        try:
            screening_input = ScreeningInput(
                screening_id=screening_id,
                jd=jd_document,
                resume=resume_document,
                external_sources=ExternalSourceInput(
                    linkedin_url=linkedin_url or None,
                    github_url=github_url or None,
                    portfolio_url=portfolio_url or None,
                    linkedin_authorized=linkedin_authorized,
                    github_authorized=github_authorized,
                    portfolio_authorized=portfolio_authorized,
                ),
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=exc.errors(include_url=False),
            ) from exc
        return _start_screening(
            screening_input=screening_input,
            jd_content=jd_content,
            resume_content=resume_content,
            response=response,
            screening_graph=screening_graph,
            app=app,
        )

    @app.post(
        "/screenings/{screening_id}/resume",
        response_model=ScreeningAPIResponse,
    )
    def resume_screening(
        screening_id: str,
        payload: InputResume,
        response: Response,
        screening_graph: ScreeningGraphPort = Depends(provide_screening_graph),
    ) -> ScreeningAPIResponse:
        if payload.screening_input.screening_id != screening_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="resume screening_id does not match requested screening",
            )
        values = _snapshot_values(screening_graph, screening_id)
        if values is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="screening not found",
            )
        current = report_from_graph_values(values)
        if (
            current.interruption is None
            or current.report.workflow_status is not WorkflowStatus.WAITING_FOR_INPUT
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="screening is not waiting for input",
            )

        return _resume_graph(
            screening_id=screening_id,
            payload=payload,
            response=response,
            screening_graph=screening_graph,
        )

    @app.post(
        "/screenings/{screening_id}/resume-upload",
        response_model=ScreeningAPIResponse,
    )
    def resume_screening_from_upload(
        screening_id: str,
        response: Response,
        jd_file: UploadFile | None = File(None),
        resume_file: UploadFile | None = File(None),
        screening_graph: ScreeningGraphPort = Depends(provide_screening_graph),
    ) -> ScreeningAPIResponse:
        values = _snapshot_values(screening_graph, screening_id)
        if values is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="screening not found")
        current = report_from_graph_values(values)
        if (
            current.interruption is None
            or current.report.workflow_status is not WorkflowStatus.WAITING_FOR_INPUT
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="screening is not waiting for input",
            )
        state, blocks, _ = from_orchestration_state(values)
        missing = set(state.required_inputs_missing)
        supplied_files = {
            "jd.extracted_content": jd_file,
            "resume.extracted_content": resume_file,
        }
        if not any(supplied_files[key] is not None for key in missing if key in supplied_files):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="upload at least one document currently required by the screening",
            )
        missing_documents = {key for key in missing if key in supplied_files}
        if any(supplied_files[key] is None for key in missing_documents):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "upload every document currently required by the screening "
                    "in one resume request"
                ),
            )
        if any(file is not None and key not in missing for key, file in supplied_files.items()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="an uploaded document is not currently required by the screening",
            )

        updated_documents = {}
        new_blocks = []
        for key, upload, field_name, source_type, kind, extractor in (
            (
                "jd.extracted_content",
                jd_file,
                "jd",
                SourceType.JD_FILE,
                InputKind.JD,
                extract_document_text,
            ),
            (
                "resume.extracted_content",
                resume_file,
                "resume",
                SourceType.RESUME_FILE,
                InputKind.RESUME,
                extract_resume_text,
            ),
        ):
            old_document = getattr(state.screening_input, field_name)
            if upload is None:
                updated_documents[field_name] = old_document
                continue
            if key not in missing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"{field_name} is not currently required by the screening",
                )
            document, content = _document_from_upload(
                upload,
                kind=kind,
                input_id=old_document.input_id,
            )
            refs = _provenance_for_document(state, old_document, source_type)
            try:
                new_blocks.extend(
                    extractor(
                        document=document,
                        content=content,
                        provenance_refs=refs,
                    )
                )
            except (ValueError, RuntimeError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{field_name} could not be extracted",
                ) from exc
            updated_documents[field_name] = document

        screening_input = state.screening_input.model_copy(update=updated_documents)
        payload = InputResume(
            screening_input=screening_input,
            extracted_blocks=(*blocks, *new_blocks),
        )
        return _resume_graph(
            screening_id=screening_id,
            payload=payload,
            response=response,
            screening_graph=screening_graph,
        )

    @app.get(
        "/screenings/{screening_id}",
        response_model=ScreeningAPIResponse,
    )
    def get_screening(
        screening_id: str,
        screening_graph: ScreeningGraphPort = Depends(provide_screening_graph),
    ) -> ScreeningAPIResponse:
        values = _snapshot_values(screening_graph, screening_id)
        if values is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="screening not found",
            )
        return report_from_graph_values(values)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request, exc: Exception):
        logger.error(
            "Unhandled screening API failure (%s)",
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "internal screening service error"},
        )

    return app
