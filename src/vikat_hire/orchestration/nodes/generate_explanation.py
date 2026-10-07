from __future__ import annotations

from collections.abc import Callable

from vikat_hire.ai.explanation import (
    ExplanationAssemblyError,
    assemble_explanation_context,
)
from vikat_hire.contracts.explanation import (
    ExplanationContext,
    ExplanationResult,
)
from vikat_hire.contracts.state import ScreeningState


ExplanationGenerator = Callable[
    [ExplanationContext],
    ExplanationResult,
]


class ExplanationGenerationNodeError(ValueError):
    """Raised when explanation-node input or output violates invariants."""


def generate_explanation_node(
    state: ScreeningState,
    *,
    generator: ExplanationGenerator,
) -> ScreeningState:
    """
    Generate and attach the recruiter-facing explanation.

    The node assembles authoritative evaluation, score, and policy artifacts
    into an ExplanationContext and passes that context to an injected
    explanation generator.

    The generator may interpret the authoritative artifacts, but the node
    does not permit it to replace or recalculate evaluation, score, policy,
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