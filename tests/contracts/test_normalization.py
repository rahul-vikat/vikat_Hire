from decimal import Decimal

import pytest
from pydantic import ValidationError

from vikat_hire.contracts.common import (
    DatePrecision,
    EvidenceConfidence,
    EvidenceStatus,
    RequirementCategory,
    RequirementImportance,
    SourceType,
)
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.normalization import (
    ExtractionKind,
    ExtractedTextBlock,
    JDExperienceRequirement,
    JDRequirement,
    NormalizedClaim,
    NormalizedExperienceRecord,
    NormalizedResponsibility,
    NormalizedScopeEvidence,
    NormalizedSkill,
    NormalizationResult,
    NormalizedSourceState,
)
from vikat_hire.contracts.scope import (
    ScopeEvidence,
    ScopeEvidenceCategory,
)


def test_extracted_text_block_requires_provenance() -> None:
    block = ExtractedTextBlock(
        block_id="block-1",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        text="Owned the authentication service end-to-end.",
        extraction_kind=ExtractionKind.PDF_TEXT,
        provenance_refs=("prov-1",),
    )

    assert block.text == "Owned the authentication service end-to-end."


def test_extracted_text_block_rejects_blank_text() -> None:
    with pytest.raises(ValidationError):
        ExtractedTextBlock(
            block_id="block-1",
            source_type=SourceType.RESUME_FILE,
            source_ref="resume-1",
            text="   ",
            extraction_kind=ExtractionKind.PDF_TEXT,
            provenance_refs=("prov-1",),
        )


def test_skill_is_observation_not_evaluation() -> None:
    skill = NormalizedSkill(
        skill_id="skill-1",
        name="Python",
        canonical_ref="python",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        evidence_status=EvidenceStatus.SUPPORTED,
        evidence_refs=("evidence-1",),
        provenance_refs=("prov-1",),
        confidence=EvidenceConfidence.HIGH,
    )

    assert skill.name == "Python"
    assert skill.canonical_ref == "python"
    assert not hasattr(skill, "score")


def test_responsibility_is_observation_not_evaluation() -> None:
    responsibility = NormalizedResponsibility(
        responsibility_id="responsibility-1",
        text="Owned the authentication service end-to-end.",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        evidence_status=EvidenceStatus.SUPPORTED,
        evidence_refs=("evidence-1",),
        provenance_refs=("prov-1",),
        confidence=EvidenceConfidence.HIGH,
    )

    assert responsibility.text.startswith("Owned")
    assert not hasattr(responsibility, "score")


def test_normalized_experience_contains_factual_data_only() -> None:
    record = NormalizedExperienceRecord(
        record_id="experience-1",
        employer="Example Corp",
        role="Senior Engineer",
        start_date=None,
        end_date=None,
        date_precision=DatePrecision.UNKNOWN,
        current=True,
        skill_refs=("skill-1",),
        responsibility_refs=("responsibility-1",),
        source_text="Senior Engineer at Example Corp.",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        evidence_refs=("evidence-1",),
        provenance_refs=("prov-1",),
    )

    evaluation_record = record.to_evaluation_record()

    assert evaluation_record.record_id == "experience-1"
    assert evaluation_record.employer == "Example Corp"
    assert evaluation_record.role == "Senior Engineer"
    assert not hasattr(evaluation_record, "raw_value")


def test_experience_date_validation_is_preserved() -> None:
    with pytest.raises(ValidationError):
        NormalizedExperienceRecord(
            record_id="experience-1",
            start_date="2025-01-01",
            end_date="2024-01-01",
            source_text="Example",
            source_type=SourceType.RESUME_FILE,
            source_ref="resume-1",
            evidence_refs=("evidence-1",),
            provenance_refs=("prov-1",),
        )


def test_jd_requirement_is_typed_separately_from_evaluation() -> None:
    requirement = JDRequirement(
        requirement_id="req-1",
        category=RequirementCategory.SKILL,
        importance=RequirementImportance.MUST_HAVE,
        text="Python",
        canonical_refs=("python",),
        source_type=SourceType.JD_FILE,
        source_ref="jd-1",
        evidence_refs=("evidence-1",),
        provenance_refs=("prov-1",),
    )

    assert requirement.category is RequirementCategory.SKILL
    assert requirement.importance is RequirementImportance.MUST_HAVE
    assert not hasattr(requirement, "score")


def test_jd_experience_requirement_has_no_candidate_result() -> None:
    requirement = JDExperienceRequirement(
        requirement_id="req-exp-1",
        importance=RequirementImportance.MUST_HAVE,
        text="5 years of Python experience",
        canonical_refs=("python",),
        source_type=SourceType.JD_FILE,
        source_ref="jd-1",
        evidence_refs=("evidence-1",),
        provenance_refs=("prov-1",),
        minimum_years=Decimal("5"),
    )

    assert requirement.category is RequirementCategory.EXPERIENCE
    assert requirement.minimum_years == Decimal("5")
    assert not hasattr(requirement, "raw_value")


def test_zero_minimum_years_is_rejected() -> None:
    with pytest.raises(ValidationError):
        JDExperienceRequirement(
            requirement_id="req-exp-1",
            importance=RequirementImportance.MUST_HAVE,
            text="experience",
            source_type=SourceType.JD_FILE,
            source_ref="jd-1",
            evidence_refs=("evidence-1",),
            provenance_refs=("prov-1",),
            minimum_years=Decimal("0"),
        )


def test_scope_normalization_contains_no_level_or_score() -> None:
    scope = NormalizedScopeEvidence(
        scope_evidence=ScopeEvidence(
            evidence_id="scope-1",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
            explicit_text="Owned the authentication service end-to-end.",
            provenance_refs=("prov-1",),
        ),
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        evidence_refs=("evidence-1",),
        provenance_refs=("prov-1",),
    )

    assert scope.scope_evidence.categories == (
        ScopeEvidenceCategory.OWNERSHIP,
    )
    assert not hasattr(scope, "candidate_level")
    assert not hasattr(scope, "score")


def test_claim_is_preserved_as_claim_not_match() -> None:
    normalized = NormalizedClaim(
        claim=Claim(
            claim_id="claim-1",
            subject="candidate",
            predicate="skill",
            value="Python",
            provenance_refs=("prov-1",),
        ),
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        evidence_status=EvidenceStatus.SUPPORTED,
        evidence_refs=("evidence-1",),
        provenance_refs=("prov-1",),
        confidence=EvidenceConfidence.HIGH,
    )

    assert normalized.claim.value == "Python"
    assert not hasattr(normalized, "match_status")
    assert not hasattr(normalized, "score")


def test_missing_source_state_is_explicit() -> None:
    result = NormalizationResult(
        screening_id="screening-1",
        source_states={
            "resume-1": NormalizedSourceState.NOT_FOUND,
        },
    )

    assert (
        result.source_states["resume-1"]
        is NormalizedSourceState.NOT_FOUND
    )


def test_unknown_source_state_reference_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NormalizationResult(
            screening_id="screening-1",
            source_states={
                "unknown-source": NormalizedSourceState.NOT_FOUND,
            },
        )


def test_normalization_result_can_contain_multiple_independent_sources() -> None:
    result = NormalizationResult(
        screening_id="screening-1",
        source_states={
            "resume-1": NormalizedSourceState.AVAILABLE,
            "linkedin-1": NormalizedSourceState.NOT_AUTHORIZED,
        },
    )

    assert len(result.source_states) == 2


def test_contradictory_claims_can_coexist_without_reconciliation() -> None:
    first = NormalizedClaim(
        claim=Claim(
            claim_id="claim-1",
            subject="candidate",
            predicate="employment",
            value="Example Corp",
            provenance_refs=("prov-1",),
        ),
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        evidence_status=EvidenceStatus.SUPPORTED,
        evidence_refs=("evidence-1",),
        provenance_refs=("prov-1",),
        confidence=EvidenceConfidence.HIGH,
    )

    second = NormalizedClaim(
        claim=Claim(
            claim_id="claim-2",
            subject="candidate",
            predicate="employment",
            value="Other Corp",
            provenance_refs=("prov-2",),
        ),
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-1",
        evidence_status=EvidenceStatus.SUPPORTED,
        evidence_refs=("evidence-2",),
        provenance_refs=("prov-2",),
        confidence=EvidenceConfidence.HIGH,
    )

    result = NormalizationResult(
        screening_id="screening-1",
        claims=(first, second),
    )

    assert len(result.claims) == 2

def test_normalized_jd_scope_evidence_converts_to_evaluation_contract() -> None:
    from vikat_hire.contracts.common import ScopeEvidenceCategory
    from vikat_hire.contracts.normalization import NormalizedJDScopeEvidence
    from vikat_hire.contracts.scope import ScopeEvidencePolarity

    normalized = NormalizedJDScopeEvidence(
        evidence_id="jd-scope-1",
        categories=(ScopeEvidenceCategory.OWNERSHIP,),
        polarity=ScopeEvidencePolarity.SUPPORTING,
        explicit_text="Own services end-to-end.",
        provenance_refs=("jd-page-1",),
    )

    result = normalized.to_evaluation_evidence()

    assert result.evidence_id == "jd-scope-1"
    assert result.categories == (ScopeEvidenceCategory.OWNERSHIP,)
    assert result.polarity is ScopeEvidencePolarity.SUPPORTING
    assert result.explicit_text == "Own services end-to-end."
    assert result.provenance_refs == ("jd-page-1",)