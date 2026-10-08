from __future__ import annotations

from collections.abc import Iterable

from vikat_hire.contracts.common import DimensionName
from vikat_hire.contracts.evaluation import (
    DimensionEvaluation,
    EvaluationResult,
)
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.dimensions import (
    DimensionEvaluationError,
    assemble_evaluation_result,
    evaluate_seniority_dimension,
)


class DimensionEvaluationNodeError(ValueError):
    """Raised when dimension-evaluation orchestration input is invalid."""


def evaluate_dimensions_node(
    state: ScreeningState,
    *,
    dimensions: Iterable[DimensionEvaluation],
    contradiction_refs: tuple[str, ...] = (),
) -> ScreeningState:
    """
    Assemble the authoritative deterministic evaluation result.

    The node does not:
    - calculate dimension values;
    - calculate scoring weights;
    - calculate the final score;
    - apply policy or eligibility;
    - interpret LLM output.

    Those responsibilities belong to their respective deterministic
    evaluation, scoring, and policy layers.
    """

    if not isinstance(state, ScreeningState):
        raise DimensionEvaluationNodeError(
            "state must be a ScreeningState"
        )

    try:
        dimension_tuple = tuple(dimensions)
    except TypeError as exc:
        raise DimensionEvaluationNodeError(
            "dimensions must be an iterable of DimensionEvaluation objects"
        ) from exc

    if any(
        not isinstance(dimension, DimensionEvaluation)
        for dimension in dimension_tuple
    ):
        raise DimensionEvaluationNodeError(
            "dimensions must contain only DimensionEvaluation objects"
        )

    if any(
        not isinstance(reference, str) or not reference.strip()
        for reference in contradiction_refs
    ):
        raise DimensionEvaluationNodeError(
            "contradiction_refs must contain only non-empty strings"
        )

    if state.scope_alignment is not None:
        if any(
            dimension.dimension is DimensionName.SENIORITY_SCOPE_ALIGNMENT
            for dimension in dimension_tuple
        ):
            raise DimensionEvaluationNodeError(
                "dimensions must not include SENIORITY_SCOPE_ALIGNMENT when "
                "state.scope_alignment is present"
            )

        try:
            seniority_dimension = evaluate_seniority_dimension(
                evaluation=state.scope_alignment.seniority_evaluation
            )
        except DimensionEvaluationError as exc:
            raise DimensionEvaluationNodeError(str(exc)) from exc

        dimension_tuple = (*dimension_tuple, seniority_dimension)

    try:
        evaluation = assemble_evaluation_result(
            screening_id=state.screening_id,
            dimensions=dimension_tuple,
            contradiction_refs=contradiction_refs,
        )
    except DimensionEvaluationError as exc:
        raise DimensionEvaluationNodeError(str(exc)) from exc

    if not isinstance(evaluation, EvaluationResult):
        raise DimensionEvaluationNodeError(
            "dimension assembly must return an EvaluationResult"
        )

    if evaluation.screening_id != state.screening_id:
        raise DimensionEvaluationNodeError(
            "evaluation screening_id does not match state screening_id"
        )

    return state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )
