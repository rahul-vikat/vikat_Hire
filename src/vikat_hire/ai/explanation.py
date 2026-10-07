from __future__ import annotations

from vikat_hire.contracts.explanation import ExplanationContext
from vikat_hire.contracts.state import ScreeningState


class ExplanationAssemblyError(ValueError):
    """Raised when authoritative explanation inputs cannot be assembled."""


def assemble_explanation_context(
    state: ScreeningState,
) -> ExplanationContext:
    """
    Assemble authoritative deterministic artifacts for explanation generation.

    This function performs no scoring, evaluation, policy, or eligibility
    calculation. It only validates that the artifacts already produced by
    authoritative components belong to the same screening and packages them
    into a typed explanation context.
    """

    if not isinstance(state, ScreeningState):
        raise ExplanationAssemblyError(
            "state must be a ScreeningState"
        )

    if state.evaluation is None:
        raise ExplanationAssemblyError(
            "explanation context requires completed evaluation"
        )

    if state.evaluation.screening_id != state.screening_id:
        raise ExplanationAssemblyError(
            "evaluation screening_id does not match state screening_id"
        )

    if (
        state.score is not None
        and state.score.screening_id != state.screening_id
    ):
        raise ExplanationAssemblyError(
            "score screening_id does not match state screening_id"
        )

    if (
        state.policy is not None
        and state.policy.screening_id != state.screening_id
    ):
        raise ExplanationAssemblyError(
            "policy screening_id does not match state screening_id"
        )

    return ExplanationContext(
        screening_id=state.screening_id,
        evaluation=state.evaluation,
        score=state.score,
        policy=state.policy,
    )