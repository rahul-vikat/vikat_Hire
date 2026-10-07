from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vikat_hire.contracts.common import (
    AccessStatus,
    ContradictionStatus,
    DerivationMethod,
    EvidenceConfidence,
    EvidenceStatus,
    SourceReliability,
    SourceType,
)
from vikat_hire.contracts.evidence import (
    Claim,
    ClaimReconciliation,
    Evidence,
    Provenance,
)
from vikat_hire.evaluation.evidence import (
    EvidenceAssemblyError,
    assemble_evidence,
)


def _provenance(provenance_id: str) -> Provenance:
    return Provenance(
        provenance_id=provenance_id,
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        method=DerivationMethod.PARSER,
        access_status=AccessStatus.AUTHORIZED,
        observed_at=datetime.now(UTC),
    )


def _claim(
    claim_id: str,
    provenance_refs: tuple[str, ...] = ("prov-1",),
) -> Claim:
    return Claim(
        claim_id=claim_id,
        subject="candidate",
        predicate="has_skill",
        value="Python",
        provenance_refs=provenance_refs,
    )


def _evidence(
    evidence_id: str,
    claim_id: str | None = "claim-1",
    provenance_refs: tuple[str, ...] = ("prov-1",),
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        claim_id=claim_id,
        status=EvidenceStatus.SUPPORTED,
        content={"skill": "Python"},
        provenance_refs=provenance_refs,
        confidence=EvidenceConfidence.HIGH,
        source_reliability=SourceReliability.SELF_REPORTED,
        supports_claim=True,
    )


def test_assembles_evidence_deterministically() -> None:
    claims = (
        _claim("claim-2"),
        _claim("claim-1"),
    )

    provenances = (
        _provenance("prov-2"),
        _provenance("prov-1"),
    )

    evidence = (
        _evidence("evidence-2", claim_id="claim-2"),
        _evidence("evidence-1", claim_id="claim-1"),
    )

    result = assemble_evidence(
        claims=claims,
        provenances=provenances,
        evidence=evidence,
        reconciliations=(),
    )

    assert result.evidence_refs == (
        "evidence-1",
        "evidence-2",
    )

    assert tuple(
        item.provenance_id
        for item in result.provenances
    ) == (
        "prov-1",
        "prov-2",
    )

    assert tuple(
        item.evidence_id
        for item in result.evidence
    ) == (
        "evidence-1",
        "evidence-2",
    )


def test_empty_evidence_is_valid_explicit_assembly() -> None:
    result = assemble_evidence(
        claims=(),
        provenances=(),
        evidence=(),
        reconciliations=(),
    )

    assert result.evidence_refs == ()
    assert result.provenances == ()
    assert result.evidence == ()


def test_claim_unknown_provenance_fails() -> None:
    with pytest.raises(
        EvidenceAssemblyError,
        match="claim references unknown provenance",
    ):
        assemble_evidence(
            claims=(
                _claim(
                    "claim-1",
                    provenance_refs=("missing-provenance",),
                ),
            ),
            provenances=(),
            evidence=(),
            reconciliations=(),
        )


def test_evidence_unknown_claim_fails() -> None:
    with pytest.raises(
        EvidenceAssemblyError,
        match="evidence references unknown claim",
    ):
        assemble_evidence(
            claims=(),
            provenances=(_provenance("prov-1"),),
            evidence=(
                _evidence(
                    "evidence-1",
                    claim_id="missing-claim",
                ),
            ),
            reconciliations=(),
        )


def test_evidence_unknown_provenance_fails() -> None:
    with pytest.raises(
        EvidenceAssemblyError,
        match="evidence references unknown provenance",
    ):
        assemble_evidence(
            claims=(_claim("claim-1"),),
            provenances=(),
            evidence=(
                _evidence("evidence-1"),
            ),
            reconciliations=(),
        )


def test_reconciliation_unknown_claim_fails() -> None:
    reconciliation = ClaimReconciliation(
        claim_id="missing-claim",
        contradiction_status=ContradictionStatus.NONE,
        rationale="No contradiction found.",
    )

    with pytest.raises(
        EvidenceAssemblyError,
        match="reconciliation references unknown claim",
    ):
        assemble_evidence(
            claims=(),
            provenances=(_provenance("prov-1"),),
            evidence=(),
            reconciliations=(reconciliation,),
        )


def test_reconciliation_unknown_evidence_fails() -> None:
    reconciliation = ClaimReconciliation(
        claim_id="claim-1",
        contradiction_status=ContradictionStatus.VALIDATED,
        supporting_evidence_refs=("missing-evidence",),
        rationale="Contradiction was validated.",
    )

    with pytest.raises(
        EvidenceAssemblyError,
        match="unknown supporting evidence",
    ):
        assemble_evidence(
            claims=(_claim("claim-1"),),
            provenances=(_provenance("prov-1"),),
            evidence=(),
            reconciliations=(reconciliation,),
        )


def test_duplicate_claim_ids_fail() -> None:
    with pytest.raises(
        EvidenceAssemblyError,
        match="duplicate claim IDs",
    ):
        assemble_evidence(
            claims=(
                _claim("claim-1"),
                _claim("claim-1"),
            ),
            provenances=(_provenance("prov-1"),),
            evidence=(),
            reconciliations=(),
        )


def test_duplicate_evidence_ids_fail() -> None:
    with pytest.raises(
        EvidenceAssemblyError,
        match="duplicate evidence IDs",
    ):
        assemble_evidence(
            claims=(_claim("claim-1"),),
            provenances=(_provenance("prov-1"),),
            evidence=(
                _evidence("evidence-1"),
                _evidence("evidence-1"),
            ),
            reconciliations=(),
        )


def test_duplicate_reconciliation_claims_fail() -> None:
    reconciliation = ClaimReconciliation(
        claim_id="claim-1",
        contradiction_status=ContradictionStatus.NONE,
        rationale="No contradiction found.",
    )

    with pytest.raises(
        EvidenceAssemblyError,
        match="duplicate reconciliation claim IDs",
    ):
        assemble_evidence(
            claims=(_claim("claim-1"),),
            provenances=(_provenance("prov-1"),),
            evidence=(),
            reconciliations=(
                reconciliation,
                reconciliation,
            ),
        )