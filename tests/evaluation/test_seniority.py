from decimal import Decimal

import pytest

from vikat_hire.contracts.common import ScopeLevel
from vikat_hire.contracts.scope import (
    JDScopeEvidence,
    ScopeEvidence,
    ScopeEvidenceCategory,
    ScopeEvidencePolarity,
)
from vikat_hire.contracts.common import (
    ExclusionReason,
    ScopeLevel,
)
from vikat_hire.evaluation.seniority import (
    evaluate_scope_alignment,
    evaluate_seniority_scope_from_evidence,
)


def _evidence(
    evidence_id: str,
    *,
    categories: tuple[ScopeEvidenceCategory, ...],
    text: str = "Explicit normalized scope evidence.",
    supervision_learning: bool = False,
) -> ScopeEvidence:
    return ScopeEvidence(
        evidence_id=evidence_id,
        categories=categories,
        supervision_learning=supervision_learning,
        explicit_text=text,
        provenance_refs=(f"prov-{evidence_id}",),
    )

def _jd_evidence(
    evidence_id: str,
    *,
    categories: tuple[ScopeEvidenceCategory, ...] = (),
    polarity: ScopeEvidencePolarity = ScopeEvidencePolarity.SUPPORTING,
    supervision_learning: bool = False,
    text: str = "Explicit JD scope evidence.",
) -> JDScopeEvidence:
    return JDScopeEvidence(
        evidence_id=evidence_id,
        categories=categories,
        supervision_learning=supervision_learning,
        polarity=polarity,
        explicit_text=text,
        provenance_refs=(f"jd-{evidence_id}",),
    )

def test_from_evidence_classifies_candidate_before_scoring() -> None:
    evidence = (
        _evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
        _evidence(
            "decision",
            categories=(
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        ),
    )

    result = evaluate_seniority_scope_from_evidence(
        evidence=evidence,
        required_level=ScopeLevel.L2,
        provenance_refs=("jd-1", "candidate-1"),
    )

    assert result.candidate_level == ScopeLevel.L2
    assert result.required_level == ScopeLevel.L2
    assert result.delta == 0
    assert result.raw_value == Decimal("100")
    assert result.evidence_refs == ("ownership", "decision")
    assert result.provenance_refs == ("jd-1", "candidate-1")


def test_from_evidence_above_required_level_uses_existing_mapping() -> None:
    evidence = (
        _evidence(
            "cross-team",
            categories=(ScopeEvidenceCategory.CROSS_TEAM_SCOPE,),
        ),
        _evidence(
            "decision",
            categories=(
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        ),
    )

    result = evaluate_seniority_scope_from_evidence(
        evidence=evidence,
        required_level=ScopeLevel.L1,
        provenance_refs=("source-1",),
    )

    assert result.candidate_level == ScopeLevel.L4
    assert result.required_level == ScopeLevel.L1
    assert result.delta == 3
    assert result.raw_value == Decimal("90")


def test_from_evidence_excludes_when_candidate_scope_is_unresolved() -> None:
    evidence = (
        _evidence(
            "production",
            categories=(
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
        ),
    )

    result = evaluate_seniority_scope_from_evidence(
        evidence=evidence,
        required_level=ScopeLevel.L2,
        provenance_refs=("source-1",),
    )

    assert result.candidate_level is None
    assert result.required_level == ScopeLevel.L2
    assert result.delta is None
    assert result.raw_value is None
    assert result.exclusion_reason is not None


def test_from_evidence_excludes_when_required_level_is_unavailable() -> None:
    evidence = (
        _evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
    )

    result = evaluate_seniority_scope_from_evidence(
        evidence=evidence,
        required_level=None,
        provenance_refs=("source-1",),
    )

    assert result.candidate_level == ScopeLevel.L1
    assert result.required_level is None
    assert result.delta is None
    assert result.raw_value is None
    assert result.exclusion_reason is not None


def test_from_evidence_l0_uses_supervision_attribute() -> None:
    evidence = (
        _evidence(
            "learning",
            categories=(),
            supervision_learning=True,
            text="Worked under direct supervision while learning the system.",
        ),
    )

    result = evaluate_seniority_scope_from_evidence(
        evidence=evidence,
        required_level=ScopeLevel.L1,
        provenance_refs=("source-1",),
    )

    assert result.candidate_level == ScopeLevel.L0
    assert result.required_level == ScopeLevel.L1
    assert result.delta == -1
    assert result.raw_value == Decimal("75")


def test_from_evidence_preserves_audit_references() -> None:
    evidence = (
        _evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
        _evidence(
            "decision",
            categories=(
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        ),
    )

    result = evaluate_seniority_scope_from_evidence(
        evidence=evidence,
        required_level=ScopeLevel.L2,
        provenance_refs=("candidate-source", "jd-source"),
    )

    assert result.evidence_refs == ("ownership", "decision")
    assert result.provenance_refs == (
        "candidate-source",
        "jd-source",
    )


def test_from_evidence_is_deterministic() -> None:
    evidence = (
        _evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
        _evidence(
            "decision",
            categories=(
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        ),
    )

    first = evaluate_seniority_scope_from_evidence(
        evidence=evidence,
        required_level=ScopeLevel.L2,
        provenance_refs=("source-1",),
    )
    second = evaluate_seniority_scope_from_evidence(
        evidence=evidence,
        required_level=ScopeLevel.L2,
        provenance_refs=("source-1",),
    )

    assert first.model_dump(
        exclude={"created_at"},
    ) == second.model_dump(
        exclude={"created_at"},
    )


def test_from_evidence_rejects_duplicate_evidence_ids() -> None:
    evidence = (
        _evidence(
            "duplicate",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
        _evidence(
            "duplicate",
            categories=(
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        ),
    )

    with pytest.raises(ValueError, match="scope evidence IDs must be unique"):
        evaluate_seniority_scope_from_evidence(
            evidence=evidence,
            required_level=ScopeLevel.L2,
            provenance_refs=("source-1",),
        )


def test_scope_alignment_integrates_jd_and_candidate_scope() -> None:
    candidate_evidence = (
        _evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
        _evidence(
            "decision",
            categories=(
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        ),
    )

    jd_evidence = (
        _jd_evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
        _jd_evidence(
            "decision",
            categories=(
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        ),
        _jd_evidence(
            "production",
            categories=(
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
        ),
    )

    result, review_required = evaluate_scope_alignment(
        candidate_evidence=candidate_evidence,
        jd_evidence=jd_evidence,
        provenance_refs=("candidate-source", "jd-source"),
    )

    assert result.candidate_level == ScopeLevel.L2
    assert result.required_level == ScopeLevel.L3
    assert result.delta == -1
    assert result.raw_value == Decimal("75")
    assert result.resolution == "evaluated"
    assert review_required is False


def test_scope_alignment_excludes_and_requests_review_for_jd_contradiction() -> None:
    candidate_evidence = (
        _evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
    )

    jd_evidence = (
        _jd_evidence(
            "ownership-support",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
            polarity=ScopeEvidencePolarity.SUPPORTING,
        ),
        _jd_evidence(
            "ownership-contradiction",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
            polarity=ScopeEvidencePolarity.CONTRADICTING,
        ),
    )

    result, review_required = evaluate_scope_alignment(
        candidate_evidence=candidate_evidence,
        jd_evidence=jd_evidence,
        provenance_refs=("candidate-source", "jd-source"),
    )

    assert result.candidate_level == ScopeLevel.L1
    assert result.required_level is None
    assert result.delta is None
    assert result.raw_value is None
    assert result.resolution == "excluded"
    assert result.exclusion_reason == (
        ExclusionReason.INSUFFICIENT_EVIDENCE
    )
    assert review_required is True


def test_scope_alignment_excludes_unresolved_jd_without_review() -> None:
    candidate_evidence = (
        _evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
    )

    jd_evidence = (
        _jd_evidence(
            "production",
            categories=(
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
        ),
    )

    result, review_required = evaluate_scope_alignment(
        candidate_evidence=candidate_evidence,
        jd_evidence=jd_evidence,
        provenance_refs=("candidate-source", "jd-source"),
    )

    assert result.candidate_level == ScopeLevel.L1
    assert result.required_level is None
    assert result.delta is None
    assert result.raw_value is None
    assert result.resolution == "excluded"
    assert result.exclusion_reason == (
        ExclusionReason.INSUFFICIENT_EVIDENCE
    )
    assert review_required is False


def test_scope_alignment_excludes_when_candidate_scope_is_unresolved() -> None:
    candidate_evidence = (
        _evidence(
            "production",
            categories=(
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
        ),
    )

    jd_evidence = (
        _jd_evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
    )

    result, review_required = evaluate_scope_alignment(
        candidate_evidence=candidate_evidence,
        jd_evidence=jd_evidence,
        provenance_refs=("candidate-source", "jd-source"),
    )

    assert result.candidate_level is None
    assert result.required_level == ScopeLevel.L1
    assert result.delta is None
    assert result.raw_value is None
    assert result.resolution == "excluded"
    assert result.exclusion_reason == (
        ExclusionReason.INSUFFICIENT_EVIDENCE
    )
    assert review_required is False


def test_scope_alignment_is_deterministic() -> None:
    candidate_evidence = (
        _evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
        _evidence(
            "decision",
            categories=(
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        ),
    )

    jd_evidence = (
        _jd_evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
        _jd_evidence(
            "decision",
            categories=(
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        ),
    )

    first, first_review = evaluate_scope_alignment(
        candidate_evidence=candidate_evidence,
        jd_evidence=jd_evidence,
        provenance_refs=("source-1",),
    )

    second, second_review = evaluate_scope_alignment(
        candidate_evidence=candidate_evidence,
        jd_evidence=jd_evidence,
        provenance_refs=("source-1",),
    )

    assert first.model_dump(
        exclude={"created_at"},
    ) == second.model_dump(
        exclude={"created_at"},
    )
    assert first_review == second_review