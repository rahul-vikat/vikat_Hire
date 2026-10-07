from __future__ import annotations

from vikat_hire.ai import ExplanationProvider
from vikat_hire.ai.explanation import (
    ExplanationAssemblyError,
    assemble_explanation_context,
)
from vikat_hire.contracts.explanation import ExplanationResult
from vikat_hire.contracts.state import ScreeningState


class ExplanationGenerationNodeError(ValueError):
    """Raised when explanation-node input or output violates invariants."""


def generate_explanation_node(
    state: ScreeningState,
    *,
    generator: ExplanationProvider,
) -> ScreeningState:
    """
    Generate and attach the recruiter-facing explanation.

    The generator receives only authoritative evaluation, score, and policy
    artifacts assembled into an ExplanationContext.

    The generator cannot replace or recalculate evaluation, score, policy,
    eligibility, or other authoritative decisions.
    """

    if not isinstance(state, ScreeningState):
        raise ExplanationGenerationNodeError(
            "state must be a ScreeningState"
        )

    if not callable(generator):
        raise ExplanationGenerationNodeError(
            "generator must be callable"
        )

    try:
        context = assemble_explanation_context(state)
    except ExplanationAssemblyError as exc:
        raise ExplanationGenerationNodeError(str(exc)) from exc

    explanation = generator(context)

    if not isinstance(explanation, ExplanationResult):
        raise ExplanationGenerationNodeError(
            "generator must return an ExplanationResult"
        )

    if explanation.screening_id != state.screening_id:
        raise ExplanationGenerationNodeError(
            "explanation screening_id does not match state screening_id"
        )

    return state.model_copy(
        update={
            "explanation": explanation,
        }
    )