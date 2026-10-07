from vikat_hire.contracts.common import SourceType, WorkflowStatus
from vikat_hire.contracts.matching import SemanticMatch
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.semantic import match_semantically


class SemanticMatchingNodeError(ValueError):
    """Invalid semantic node input or result."""


def match_semantic_node(state: ScreeningState, *, requirement: JDRequirement) -> ScreeningState:
    """Attach one deterministic semantic result; LLM proposals are not inputs."""
    if not isinstance(state, ScreeningState):
        raise SemanticMatchingNodeError("state must be a ScreeningState")
    if not isinstance(requirement, JDRequirement):
        raise SemanticMatchingNodeError("requirement must be a JDRequirement")
    requirement = JDRequirement.model_validate(requirement.model_dump())
    if requirement.source_type is not SourceType.JD_FILE:
        raise SemanticMatchingNodeError("requirement must come from a JD")
    state = ScreeningState.model_validate(state.model_dump())
    if state.screening_input.screening_id != state.screening_id:
        raise SemanticMatchingNodeError("input screening_id does not match state")
    if state.required_inputs_missing or state.status is WorkflowStatus.WAITING_FOR_INPUT:
        raise SemanticMatchingNodeError("required input must be resolved before matching")
    if any(
        match.requirement_id == requirement.requirement_id
        for match in state.deterministic_semantic_matches
    ):
        raise SemanticMatchingNodeError("semantic match already exists for requirement")
    result = match_semantically(
        requirement_id=requirement.requirement_id,
        requirement_skill_refs=requirement.canonical_refs,
        candidate_claims=state.claims,
        keyword_matches=state.keyword_matches,
    )
    if not isinstance(result, SemanticMatch):
        raise SemanticMatchingNodeError("matcher must return a SemanticMatch")
    result = SemanticMatch.model_validate(result.model_dump())
    if result.requirement_id != requirement.requirement_id:
        raise SemanticMatchingNodeError("matcher returned a different requirement_id")
    if result.candidate_claim_id is not None and result.candidate_claim_id not in {
        claim.claim_id for claim in state.claims
    }:
        raise SemanticMatchingNodeError("matcher returned an unknown candidate claim")
    if any(match.match_id == result.match_id for match in state.deterministic_semantic_matches):
        raise SemanticMatchingNodeError("duplicate semantic match ID")
    return state.model_copy(
        update={
            "deterministic_semantic_matches": (*state.deterministic_semantic_matches, result),
        }
    )
