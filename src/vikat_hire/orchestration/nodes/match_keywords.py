from vikat_hire.contracts.common import SourceType, WorkflowStatus
from vikat_hire.contracts.matching import KeywordMatch
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.keyword_matcher import (
    KeywordDefinition,
    RequirementKeyword,
    match_requirement,
)


class KeywordMatchingNodeError(ValueError):
    """Invalid keyword node input or result."""


def match_keywords_node(
    state: ScreeningState,
    *,
    requirement: JDRequirement,
    vocabulary: KeywordDefinition | None = None,
) -> ScreeningState:
    """Match one JD requirement using only the existing deterministic service."""
    if not isinstance(state, ScreeningState):
        raise KeywordMatchingNodeError("state must be a ScreeningState")
    if not isinstance(requirement, JDRequirement):
        raise KeywordMatchingNodeError("requirement must be a JDRequirement")
    requirement = JDRequirement.model_validate(requirement.model_dump())
    if requirement.source_type is not SourceType.JD_FILE:
        raise KeywordMatchingNodeError("requirement must come from a JD")
    if vocabulary is not None and not isinstance(vocabulary, KeywordDefinition):
        raise KeywordMatchingNodeError("vocabulary must be a KeywordDefinition")
    state = ScreeningState.model_validate(state.model_dump())
    if state.screening_input.screening_id != state.screening_id:
        raise KeywordMatchingNodeError("input screening_id does not match state")
    if state.required_inputs_missing or state.status is WorkflowStatus.WAITING_FOR_INPUT:
        raise KeywordMatchingNodeError("required input must be resolved before matching")
    if any(match.requirement_id == requirement.requirement_id for match in state.keyword_matches):
        raise KeywordMatchingNodeError("keyword matches already exist for requirement")
    claim_ids = {claim.claim_id for claim in state.claims}
    if len(claim_ids) != len(state.claims):
        raise KeywordMatchingNodeError("duplicate candidate claim IDs")
    result = match_requirement(
        requirement=RequirementKeyword(
            requirement_id=requirement.requirement_id,
            text=requirement.text,
            vocabulary=vocabulary,
        ),
        claims=state.claims,
    )
    if not isinstance(result, tuple) or any(not isinstance(item, KeywordMatch) for item in result):
        raise KeywordMatchingNodeError("matcher must return a tuple of KeywordMatch")
    result = tuple(KeywordMatch.model_validate(match.model_dump()) for match in result)
    seen = {match.match_id for match in state.keyword_matches}
    for match in result:
        if match.requirement_id != requirement.requirement_id:
            raise KeywordMatchingNodeError("matcher returned a different requirement_id")
        if match.candidate_claim_id not in claim_ids:
            raise KeywordMatchingNodeError("matcher returned an unknown candidate claim")
        if match.match_id in seen:
            raise KeywordMatchingNodeError("duplicate keyword match ID")
        seen.add(match.match_id)
    return state.model_copy(update={"keyword_matches": (*state.keyword_matches, *result)})
