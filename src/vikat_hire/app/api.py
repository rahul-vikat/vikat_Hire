from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import JSONResponse
from langgraph.types import Command

from vikat_hire.app.dependencies import (
    ApplicationDependencyError,
    ScreeningAPIResponse,
    ScreeningGraphPort,
    ScreeningSubmission,
    build_initial_screening_state,
    provide_screening_graph,
    report_from_graph_values,
)
from vikat_hire.contracts.common import WorkflowStatus
from vikat_hire.orchestration.graph import invoke_screening_graph
from vikat_hire.orchestration.interrupts import InputInterruptionError, InputResume

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
        screening_id = submission.screening_input.screening_id
        registry = getattr(app.state, "screening_id_registry", None)
        reserved = False
        if registry is not None:
            if not registry.reserve(screening_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="screening_id already exists",
                )
            reserved = True
            # Protect checkpoints created before the registry was introduced
            # (or by another approved graph entrypoint).
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
            state = build_initial_screening_state(submission.screening_input)
            output = invoke_screening_graph(
                screening_graph,
                state,
                jd_content=submission.jd_content,
                resume_content=submission.resume_content,
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
