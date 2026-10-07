from __future__ import annotations

from collections.abc import Iterable

from vikat_hire.contracts.evaluation import (
    DimensionEvaluation,
    EvaluationResult,
)
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.dimensions import (
    DimensionEvaluationError,
    assemble_evaluation_result,
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

    dimension_tuple = tuple(dimensions)

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