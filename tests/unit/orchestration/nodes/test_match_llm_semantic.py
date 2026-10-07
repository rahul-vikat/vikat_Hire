from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.ai.llm_semantic import (
    LLMSemanticDraft,
    LLMSemanticMatcher,
)
from vikat_hire.contracts.common import (
    EvidenceConfidence,
    EvidenceStatus,
    MatchStatus,
    RequirementCategory,
    RequirementImportance,
    SourceReliability,
    SourceType,
)
from vikat_hire.contracts.evidence import Claim, Evidence
from vikat_hire.contracts.matching import SemanticMatch
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.nodes.match_llm_semantic import (
    LLMSemanticNodeError,
    match_llm_semantic_node,
)


def _requirement() -> JDRequirement:
    return JDRequirement(
        requirement_id="req-1",
        category=RequirementCategory.SKILL,
        importance=RequirementImportance.MUST_HAVE,
        text="Python experience",
        canonical_refs=("skill:python",),
        source_type=SourceType.JD_FILE,
        source_ref="jd-1",
        evidence_refs=("jd-evidence-1",),
        provenance_refs=("jd-prov-1",),
    )


def _claim(
    *,
    claim_id: str = "claim-1",
    value: str = "Python",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        subject="candidate",
        predicate="skill",
        value=value,
        provenance_refs=("resume-prov-1",),
    )


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="evidence-1",
        claim_id="claim-1",
        status=EvidenceStatus.SUPPORTED,
        content="Python",
        provenance_refs=("resume-prov-1",),
        confidence=EvidenceConfidence.HIGH,
        source_reliability=SourceReliability.SELF_REPORTED,
        supports_claim=True,
    )


def _deterministic_match(
    *,
    requirement_id: str = "req-1",
    candidate_claim_id: str | None = "claim-1",
) -> SemanticMatch:
    return SemanticMatch(
        match_id="semantic:req-1:claim-1",
        requirement_id=requirement_id,
        candidate_claim_id=candidate_claim_id,
        status=MatchStatus.MATCHED,
        score=Decimal("100"),
        rationale="Canonical skill reference matched deterministically.",
        provenance_refs=("resume-prov-1",),
    )


def _state() -> ScreeningState:
    from vikat_hire.contracts.inputs import (
        DocumentInput,
        ScreeningInput,
    )
    from vikat_hire.contracts.common import InputKind

    screening_input = ScreeningInput(
        screening_id="screening-1",
        jd=DocumentInput(
            kind=InputKind.JD,
            filename="jd.pdf",
            media_type="application/pdf",
            content_hash="jd-hash",
            storage_ref="jd-storage",
        ),
        resume=DocumentInput(
            kind=InputKind.RESUME,
            filename="resume.pdf",
            media_type="application/pdf",
            content_hash="resume-hash",
            storage_ref="resume-storage",
        ),
    )

    return ScreeningState(
        screening_id="screening-1",
        screening_input=screening_input,
        claims=(_claim(),),
        evidence=(_evidence(),),
        deterministic_semantic_matches=(
            _deterministic_match(),
        ),
    )


def _matcher(
    *,
    draft: LLMSemanticDraft | None,
) -> LLMSemanticMatcher:
    def provider(_context):
        return draft

    return LLMSemanticMatcher(
        provider=provider,
        model_config_ref="test-model-config",
        provenance_refs=("llm-prov-1",),
    )


def test_node_attaches_valid_llm_proposal() -> None:
    state = _state()

    draft = LLMSemanticDraft(
        score=Decimal("92.50"),
        candidate_claim_id="claim-1",
        rationale="Candidate claim directly supports the requirement.",
    )

    result = match_llm_semantic_node(
        state,
        requirement=_requirement(),
        deterministic_match=_deterministic_match(),
        matcher=_matcher(draft=draft),
    )

    assert len(result.llm_semantic_proposals) == 1

    proposal = result.llm_semantic_proposals[0]

    assert proposal.requirement_id == "req-1"
    assert proposal.candidate_claim_id == "claim-1"
    assert proposal.score == Decimal("92.50")


def test_node_preserves_deterministic_match() -> None:
    state = _state()
    deterministic_match = _deterministic_match()

    result = match_llm_semantic_node(
        state,
        requirement=_requirement(),
        deterministic_match=deterministic_match,
        matcher=_matcher(
            draft=LLMSemanticDraft(
                score=Decimal("20"),
                candidate_claim_id="claim-1",
                rationale="LLM proposes a lower semantic fit.",
            )
        ),
    )

    assert (
        result.deterministic_semantic_matches
        == state.deterministic_semantic_matches
    )


def test_node_does_not_attach_when_provider_returns_none() -> None:
    state = _state()

    result = match_llm_semantic_node(
        state,
        requirement=_requirement(),
        deterministic_match=_deterministic_match(),
        matcher=_matcher(draft=None),
    )

    assert result.llm_semantic_proposals == ()


def test_node_preserves_existing_proposals_for_other_requirements() -> None:
    state = _state()

    first = match_llm_semantic_node(
        state,
        requirement=_requirement(),
        deterministic_match=_deterministic_match(),
        matcher=_matcher(
            draft=LLMSemanticDraft(
                score=Decimal("90"),
                candidate_claim_id="claim-1",
                rationale="Strong supporting claim.",
            )
        ),
    )

    other_proposal = first.llm_semantic_proposals[0].model_copy(
        update={
            "requirement_id": "req-2",
        }
    )

    state_with_other = first.model_copy(
        update={
            "llm_semantic_proposals": (other_proposal,),
        }
    )

    result = match_llm_semantic_node(
        state_with_other,
        requirement=_requirement(),
        deterministic_match=_deterministic_match(),
        matcher=_matcher(draft=None),
    )

    assert result.llm_semantic_proposals == (other_proposal,)


def test_node_rejects_mismatched_deterministic_requirement() -> None:
    with pytest.raises(
        LLMSemanticNodeError,
        match="requirement_id does not match",
    ):
        match_llm_semantic_node(
            _state(),
            requirement=_requirement(),
            deterministic_match=_deterministic_match(
                requirement_id="req-2",
            ),
            matcher=_matcher(draft=None),
        )


def test_node_rejects_duplicate_proposal_for_requirement() -> None:
    state = _state()

    state = state.model_copy(
        update={
            "llm_semantic_proposals": (
                _matcher(
                    draft=LLMSemanticDraft(
                        score=Decimal("90"),
                        candidate_claim_id="claim-1",
                        rationale="Existing proposal.",
                    )
                ).propose(
                    requirement=_requirement(),
                    candidate_claims=state.claims,
                    candidate_evidence=state.evidence,
                    deterministic_match=_deterministic_match(),
                ),
            )
        },
    )

    with pytest.raises(
        LLMSemanticNodeError,
        match="already exists",
    ):
        match_llm_semantic_node(
            state,
            requirement=_requirement(),
            deterministic_match=_deterministic_match(),
            matcher=_matcher(draft=None),
        )


def test_node_rejects_non_state_input() -> None:
    with pytest.raises(
        LLMSemanticNodeError,
        match="state must be a ScreeningState",
    ):
        match_llm_semantic_node(
            object(),
            requirement=_requirement(),
            deterministic_match=_deterministic_match(),
            matcher=_matcher(draft=None),
        )


def test_node_rejects_non_requirement_input() -> None:
    with pytest.raises(
        LLMSemanticNodeError,
        match="requirement must be a JDRequirement",
    ):
        match_llm_semantic_node(
            _state(),
            requirement=object(),
            deterministic_match=_deterministic_match(),
            matcher=_matcher(draft=None),
        )


def test_node_rejects_non_matcher_input() -> None:
    with pytest.raises(
        LLMSemanticNodeError,
        match="matcher must be an LLMSemanticMatcher",
    ):
        match_llm_semantic_node(
            _state(),
            requirement=_requirement(),
            deterministic_match=_deterministic_match(),
            matcher=object(),
        )
