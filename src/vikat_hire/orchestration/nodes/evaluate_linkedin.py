from __future__ import annotations

from vikat_hire.contracts.evaluation import DimensionEvaluation, EvaluationResult
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.linkedin_match import (
    LinkedInEvaluationError,
    evaluate_linkedin_evidence,
)


class LinkedInEvaluationNodeError(ValueError):
    """Raised when LinkedIn-evaluation orchestration input is invalid."""


def evaluate_linkedin_node(
    state: ScreeningState,
) -> ScreeningState:
    """
    Evaluate LinkedIn evidence and attach the resulting dimension.

    The deterministic LinkedIn evaluator is the sole authority for the
    LinkedIn dimension value.

    This node does not:
    - fetch LinkedIn data;
    - normalize LinkedIn data;
    - infer candidate claims;
    - calculate the final screening score;
    - apply policy;
    - interpret LLM output.
    """

    if not isinstance(state, ScreeningState):
        raise LinkedInEvaluationNodeError(
            "state must be a ScreeningState"
        )

    if state.evaluation is not None:
        if state.evaluation.screening_id != state.screening_id:
            raise LinkedInEvaluationNodeError(
                "evaluation screening_id does not match state screening_id"
            )

    try:
        linkedin_dimension = evaluate_linkedin_evidence(
            claims=state.claims,
            evidence=state.evidence,
            provenances=state.provenances,
            reconciliations=state.reconciliations,
        )
    except LinkedInEvaluationError as exc:
        raise LinkedInEvaluationNodeError(str(exc)) from exc

    if not isinstance(linkedin_dimension, DimensionEvaluation):
        raise LinkedInEvaluationNodeError(
            "LinkedIn evaluator must return a DimensionEvaluation"
        )

    if state.evaluation is None:
        evaluation = EvaluationResult(
            screening_id=state.screening_id,
            dimensions=(linkedin_dimension,),
            contradiction_refs=(),
            deterministic=True,
        )
    else:
        existing_dimensions = tuple(
            dimension
            for dimension in state.evaluation.dimensions
            if dimension.dimension != linkedin_dimension.dimension
        )

        evaluation = EvaluationResult(
            screening_id=state.screening_id,
            dimensions=existing_dimensions + (linkedin_dimension,),
            contradiction_refs=state.evaluation.contradiction_refs,
            deterministic=True,
        )

    return state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )