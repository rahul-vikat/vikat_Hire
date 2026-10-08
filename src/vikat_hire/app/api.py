from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response, status
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


def create_app(*, graph: ScreeningGraphPort) -> FastAPI:
    """Create the HTTP boundary around an explicitly injected screening graph."""
    if not callable(getattr(graph, "invoke", None)) or not callable(
        getattr(graph, "get_state", None)
    ):
        raise ApplicationDependencyError(
            "graph must provide invoke() and get_state()"
        )
    if getattr(graph, "checkpointer", None) is None:
        raise ApplicationDependencyError(
            "graph must be compiled with an injected LangGraph checkpointer"
        )

    app = FastAPI(title="VikatHire API")
    app.state.screening_graph = graph

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
        if _snapshot_values(screening_graph, screening_id) is not None:
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
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
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
        logger.exception("Unhandled screening API failure", exc_info=exc)
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "internal screening service error"},
        )

    return app
