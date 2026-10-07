from __future__ import annotations

from vikat_hire.ai.llm_semantic import (
    LLMSemanticMatcher,
    LLMSemanticMatchingError,
)
from vikat_hire.contracts.matching import SemanticMatch
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.contracts.state import ScreeningState


class LLMSemanticNodeError(ValueError):
    """Raised when LLM semantic orchestration input is invalid."""


def match_llm_semantic_node(
    state: ScreeningState,
    *,
    requirement: JDRequirement,
    deterministic_match: SemanticMatch,
    matcher: LLMSemanticMatcher,
) -> ScreeningState:
    """
    Generate one LLM semantic proposal for one JD requirement.

    The deterministic SemanticMatch is supplied as authoritative context.
    This node only attaches the resulting LLM proposal to state.

    The node never:
    - changes the deterministic semantic match;
    - calculates or modifies scores;
    - changes evaluation;
    - changes policy or eligibility;
    - treats an LLM proposal as authoritative.

    A provider returning no proposal leaves the existing proposal collection
    unchanged.
    """

    if not isinstance(state, ScreeningState):
        raise LLMSemanticNodeError(
            "state must be a ScreeningState"
        )

    if not isinstance(requirement, JDRequirement):
        raise LLMSemanticNodeError(
            "requirement must be a JDRequirement"
        )

    if not isinstance(deterministic_match, SemanticMatch):
        raise LLMSemanticNodeError(
            "deterministic_match must be a SemanticMatch"
        )

    if not isinstance(matcher, LLMSemanticMatcher):
        raise LLMSemanticNodeError(
            "matcher must be an LLMSemanticMatcher"
        )

    if (
        deterministic_match.requirement_id
        != requirement.requirement_id
    ):
        raise LLMSemanticNodeError(
            "deterministic semantic match requirement_id does not "
            "match the JD requirement"
        )

    existing_for_requirement = tuple(
        proposal
        for proposal in state.llm_semantic_proposals
        if proposal.requirement_id == requirement.requirement_id
    )

    if existing_for_requirement:
        raise LLMSemanticNodeError(
            "LLM semantic proposal already exists for JD requirement: "
            f"{requirement.requirement_id}"
        )

    try:
        proposal = matcher.propose(
            requirement=requirement,
            candidate_claims=state.claims,
            candidate_evidence=state.evidence,
            deterministic_match=deterministic_match,
        )
    except LLMSemanticMatchingError as exc:
        raise LLMSemanticNodeError(str(exc)) from exc

    if proposal is None:
        return state

    if proposal.requirement_id != requirement.requirement_id:
        raise LLMSemanticNodeError(
            "LLM semantic proposal requirement_id does not match "
            "the JD requirement"
        )

    if (
        proposal.candidate_claim_id is not None
        and proposal.candidate_claim_id
        not in {claim.claim_id for claim in state.claims}
    ):
        raise LLMSemanticNodeError(
            "LLM semantic proposal references a claim not present "
            "in screening state"
        )

    return state.model_copy(
        update={
            "llm_semantic_proposals": (
                *state.llm_semantic_proposals,
                proposal,
            )
        }
    )
