from decimal import Decimal

import pytest

from vikat_hire.contracts.common import ScopeLevel
from vikat_hire.contracts.scope import ScopeEvidence, ScopeEvidenceCategory
from vikat_hire.evaluation.seniority import (
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