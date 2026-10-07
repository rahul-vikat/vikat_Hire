from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.ai.llm_semantic import (
    LLMSemanticDraft,
    LLMSemanticMatcher,
    LLMSemanticMatchingError,
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


def _deterministic_match() -> SemanticMatch:
    return SemanticMatch(
        match_id="semantic:req-1:claim-1",
        requirement_id="req-1",
        candidate_claim_id="claim-1",
        status=MatchStatus.MATCHED,
        score=Decimal("100"),
        rationale="Canonical skill reference matched deterministically.",
        provenance_refs=("resume-prov-1",),
    )


class FakeProvider:
    def __init__(
        self,
        result: LLMSemanticDraft | None,
    ) -> None:
        self.result = result
        self.context = None

    def __call__(self, context):
        self.context = context
        return self.result


def _matcher(
    provider: FakeProvider,
) -> LLMSemanticMatcher:
    return LLMSemanticMatcher(
        provider=provider,
        model_config_ref="llm-semantic-test-v1",
        provenance_refs=("llm-prov-1",),
    )


def test_valid_proposal_is_constructed_by_application_boundary() -> None:
    provider = FakeProvider(
        LLMSemanticDraft(
            score=Decimal("87.50"),
            candidate_claim_id="claim-1",
            rationale="The supplied claim directly supports the requirement.",
        )
    )

    result = _matcher(provider).propose(
        requirement=_requirement(),
        candidate_claims=(_claim(),),
        candidate_evidence=(_evidence(),),
        deterministic_match=_deterministic_match(),
    )

    assert result is not None
    assert result.requirement_id == "req-1"
    assert result.candidate_claim_id == "claim-1"
    assert result.score == Decimal("87.50")
    assert result.rationale == (
        "The supplied claim directly supports the requirement."
    )
    assert result.model_config_ref == "llm-semantic-test-v1"
    assert result.provenance_refs == ("llm-prov-1",)


def test_provider_receives_only_one_requirement_context() -> None:
    provider = FakeProvider(
        LLMSemanticDraft(
            score=Decimal("90"),
            candidate_claim_id="claim-1",
            rationale="Supported by the supplied claim.",
        )
    )

    _matcher(provider).propose(
        requirement=_requirement(),
        candidate_claims=(_claim(),),
        candidate_evidence=(_evidence(),),
        deterministic_match=_deterministic_match(),
    )

    assert provider.context is not None
    assert provider.context.requirement.requirement_id == "req-1"
    assert provider.context.deterministic_match.requirement_id == "req-1"
    assert len(provider.context.candidate_claims) == 1
    assert len(provider.context.candidate_evidence) == 1


def test_no_provider_proposal_returns_none() -> None:
    provider = FakeProvider(None)

    result = _matcher(provider).propose(
        requirement=_requirement(),
        candidate_claims=(_claim(),),
        candidate_evidence=(_evidence(),),
        deterministic_match=_deterministic_match(),
    )

    assert result is None


def test_unknown_claim_reference_is_rejected() -> None:
    provider = FakeProvider(
        LLMSemanticDraft(
            score=Decimal("90"),
            candidate_claim_id="invented-claim",
            rationale="Unsupported proposal.",
        )
    )

    with pytest.raises(
        LLMSemanticMatchingError,
        match="unknown candidate claim",
    ):
        _matcher(provider).propose(
            requirement=_requirement(),
            candidate_claims=(_claim(),),
            candidate_evidence=(_evidence(),),
            deterministic_match=_deterministic_match(),
        )


@pytest.mark.parametrize(
    "score",
    [
        Decimal("-0.01"),
        Decimal("100.01"),
    ],
)
def test_invalid_provider_score_is_rejected(score: Decimal) -> None:
    with pytest.raises(ValueError):
        LLMSemanticDraft(
            score=score,
            candidate_claim_id="claim-1",
            rationale="Proposal.",
        )


def test_deterministic_match_is_not_modified() -> None:
    deterministic_match = _deterministic_match()

    provider = FakeProvider(
        LLMSemanticDraft(
            score=Decimal("50"),
            candidate_claim_id="claim-1",
            rationale="The model disagrees with the deterministic result.",
        )
    )

    _matcher(provider).propose(
        requirement=_requirement(),
        candidate_claims=(_claim(),),
        candidate_evidence=(_evidence(),),
        deterministic_match=deterministic_match,
    )

    assert deterministic_match.model_dump(
        exclude={"created_at"},
    ) == _deterministic_match().model_dump(
        exclude={"created_at"},
    )


def test_evidence_unknown_claim_is_rejected() -> None:
    provider = FakeProvider(None)

    invalid_evidence = Evidence(
        evidence_id="evidence-1",
        claim_id="missing-claim",
        status=EvidenceStatus.SUPPORTED,
        content="Python",
        provenance_refs=("resume-prov-1",),
        confidence=EvidenceConfidence.HIGH,
        source_reliability=SourceReliability.SELF_REPORTED,
        supports_claim=True,
    )

    with pytest.raises(
        ValueError,
        match="references unknown claim",
    ):
        _matcher(provider).propose(
            requirement=_requirement(),
            candidate_claims=(_claim(),),
            candidate_evidence=(invalid_evidence,),
            deterministic_match=_deterministic_match(),
        )


def test_provider_output_must_be_a_draft_or_none() -> None:
    provider = FakeProvider("invalid")

    with pytest.raises(
        LLMSemanticMatchingError,
        match="LLMSemanticDraft or None",
    ):
        _matcher(provider).propose(
            requirement=_requirement(),
            candidate_claims=(_claim(),),
            candidate_evidence=(_evidence(),),
            deterministic_match=_deterministic_match(),
        )


def test_missing_provenance_is_rejected_at_application_boundary() -> None:
    provider = FakeProvider(None)

    with pytest.raises(
        LLMSemanticMatchingError,
        match="provenance_refs must not be empty",
    ):
        LLMSemanticMatcher(
            provider=provider,
            model_config_ref="llm-semantic-test-v1",
            provenance_refs=(),
        )
