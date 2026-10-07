from decimal import Decimal
from importlib import import_module

import pytest

from vikat_hire.contracts.common import (
    MatchStatus,
    RequirementCategory,
    RequirementImportance,
    SourceType,
    WorkflowStatus,
)
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.matching import LLMSemanticProposal
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.evaluation.keyword_matcher import (
    KeywordDefinition,
    RequirementKeyword,
    match_requirement,
)
from vikat_hire.evaluation.semantic import match_semantically
from vikat_hire.orchestration.nodes.match_keywords import match_keywords_node
from vikat_hire.orchestration.nodes.match_semantic import match_semantic_node


@pytest.fixture
def requirement():
    return JDRequirement(
        requirement_id="req-1",
        text="Python",
        category=RequirementCategory.SKILL,
        importance=RequirementImportance.MUST_HAVE,
        source_type=SourceType.JD_FILE,
        source_ref="jd-block-1",
        evidence_refs=("jd-block-1:line:1",),
        provenance_refs=("jd-prov",),
    )


@pytest.fixture
def candidate_state(screening_state):
    return screening_state.model_copy(
        update={
            "claims": (
                Claim(
                    claim_id="claim-1",
                    subject="candidate",
                    predicate="skill",
                    value="Python",
                    provenance_refs=("resume-prov",),
                ),
            )
        }
    )


@pytest.fixture(params=[match_keywords_node, match_semantic_node])
def node(request):
    return request.param


def test_keyword_adapter_matches_domain_service_and_preserves_state(candidate_state, requirement):
    result = match_keywords_node(candidate_state, requirement=requirement)
    expected = match_requirement(
        requirement=RequirementKeyword("req-1", "Python"), claims=candidate_state.claims
    )
    assert result.keyword_matches == expected
    for field in type(candidate_state).model_fields:
        if field != "keyword_matches":
            assert getattr(result, field) == getattr(candidate_state, field)
    assert candidate_state.keyword_matches == ()


def test_semantic_adapter_uses_only_deterministic_evidence(candidate_state, requirement):
    state = match_keywords_node(candidate_state, requirement=requirement)
    state = state.model_copy(
        update={
            "llm_semantic_proposals": (
                LLMSemanticProposal(
                    requirement_id="req-1",
                    candidate_claim_id="claim-1",
                    score=Decimal("1"),
                    rationale="Disagreeing proposal",
                    model_config_ref="test-model",
                    provenance_refs=("llm-prov",),
                ),
            )
        }
    )
    result = match_semantic_node(state, requirement=requirement)
    expected = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=state.claims,
        keyword_matches=state.keyword_matches,
    )
    assert result.deterministic_semantic_matches[0].model_dump(
        exclude={"created_at"}
    ) == expected.model_dump(exclude={"created_at"})
    assert result.deterministic_semantic_matches[0].score == Decimal("100")
    for field in type(state).model_fields:
        if field != "deterministic_semantic_matches":
            assert getattr(result, field) == getattr(state, field)


def test_no_evidence_keeps_existing_domain_semantics(screening_state, requirement):
    assert match_keywords_node(screening_state, requirement=requirement).keyword_matches == ()
    result = match_semantic_node(screening_state, requirement=requirement)
    assert result.deterministic_semantic_matches[0].status is MatchStatus.UNRESOLVED


def test_configured_vocabulary_is_forwarded(candidate_state, requirement):
    requirement = requirement.model_copy(update={"text": "language"})
    result = match_keywords_node(
        candidate_state,
        requirement=requirement,
        vocabulary=KeywordDefinition(canonical_ref="language", synonyms=("Python",)),
    )
    assert result.keyword_matches[0].score == Decimal("95")
    assert result.keyword_matches[0].match_type == "synonym"


def test_canonical_refs_are_forwarded(candidate_state, requirement):
    requirement = requirement.model_copy(update={"canonical_refs": ("Python",)})
    result = match_semantic_node(candidate_state, requirement=requirement)
    assert result.deterministic_semantic_matches[0].status is MatchStatus.MATCHED
    assert result.deterministic_semantic_matches[0].score == Decimal("100")


def test_duplicate_work_fails_and_other_requirements_are_preserved(
    candidate_state, requirement, node
):
    first = node(candidate_state, requirement=requirement)
    with pytest.raises(ValueError, match="already exist"):
        node(first, requirement=requirement)
    second = node(first, requirement=requirement.model_copy(update={"requirement_id": "req-2"}))
    field = "keyword_matches" if node is match_keywords_node else "deterministic_semantic_matches"
    assert getattr(second, field)[0] == getattr(first, field)[0]
    assert len(getattr(second, field)) == 2


@pytest.mark.parametrize(
    "invalid", ["state", "requirement", "identity", "source", "duplicate_claims"]
)
def test_invalid_matching_inputs_fail(candidate_state, requirement, node, invalid):
    state = candidate_state
    if invalid == "state":
        state = None
    elif invalid == "requirement":
        requirement = None
    elif invalid == "identity":
        state = state.model_copy(update={"screening_id": "other"})
    elif invalid == "source":
        requirement = requirement.model_copy(update={"source_type": SourceType.RESUME_FILE})
    else:
        state = state.model_copy(update={"claims": (*state.claims, *state.claims)})
    with pytest.raises(ValueError):
        node(state, requirement=requirement)


@pytest.mark.parametrize("invalid", ["type", "requirement", "claim", "duplicate"])
def test_invalid_matcher_results_fail(candidate_state, requirement, node, monkeypatch, invalid):
    module = import_module(node.__module__)
    if node is match_keywords_node:
        service_name = "match_requirement"
        match = match_requirement(
            requirement=RequirementKeyword("req-1", "Python"), claims=candidate_state.claims
        )[0]
    else:
        service_name = "match_semantically"
        match = match_semantically(
            requirement_id="req-1",
            requirement_skill_refs=("Python",),
            candidate_claims=candidate_state.claims,
            keyword_matches=(),
        )
    if invalid == "type":
        output = None
    else:
        updates = {
            "requirement": {"requirement_id": "other"},
            "claim": {"candidate_claim_id": "unknown"},
            "duplicate": {},
        }[invalid]
        match = match.model_copy(update=updates)
        output = (match,) if node is match_keywords_node else match
        if invalid == "duplicate":
            if node is match_keywords_node:
                output = (match, match)
            else:
                candidate_state = candidate_state.model_copy(
                    update={
                        "deterministic_semantic_matches": (
                            match.model_copy(update={"requirement_id": "other"}),
                        ),
                    }
                )
    monkeypatch.setattr(module, service_name, lambda **kwargs: output)
    with pytest.raises(ValueError):
        node(candidate_state, requirement=requirement)


def test_matcher_failure_is_not_swallowed(candidate_state, requirement, node, monkeypatch):
    error = RuntimeError("domain failure")

    def fail(**kwargs):
        raise error

    service = "match_requirement" if node is match_keywords_node else "match_semantically"
    monkeypatch.setattr(import_module(node.__module__), service, fail)
    with pytest.raises(RuntimeError) as raised:
        node(candidate_state, requirement=requirement)
    assert raised.value is error


@pytest.mark.parametrize(
    "updates",
    [
        {"status": WorkflowStatus.WAITING_FOR_INPUT},
        {"required_inputs_missing": ("resume.extracted_content",)},
    ],
)
def test_missing_input_cannot_proceed_to_matching(candidate_state, requirement, node, updates):
    with pytest.raises(ValueError, match="required input must be resolved"):
        node(candidate_state.model_copy(update=updates), requirement=requirement)
