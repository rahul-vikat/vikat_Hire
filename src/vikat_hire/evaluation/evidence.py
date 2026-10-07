from __future__ import annotations

from vikat_hire.contracts.evidence import (
    Claim,
    ClaimReconciliation,
    Evidence,
    EvidenceBundle,
    Provenance,
)


class EvidenceAssemblyError(ValueError):
    """Raised when evidence cannot be assembled consistently."""


def assemble_evidence(
    *,
    claims: tuple[Claim, ...],
    provenances: tuple[Provenance, ...],
    evidence: tuple[Evidence, ...],
    reconciliations: tuple[ClaimReconciliation, ...],
) -> EvidenceBundle:
    """
    Validate and deterministically assemble the existing evidence graph.

    This function does not evaluate candidate suitability, calculate scores,
    resolve contradictions, or interpret LLM proposals.

    It only verifies that claims, evidence, provenance, and reconciliation
    references point to existing objects and returns them in deterministic
    order.
    """

    _validate_unique_ids(
        objects=claims,
        object_name="claim",
        object_id=lambda item: item.claim_id,
    )
    _validate_unique_ids(
        objects=provenances,
        object_name="provenance",
        object_id=lambda item: item.provenance_id,
    )
    _validate_unique_ids(
        objects=evidence,
        object_name="evidence",
        object_id=lambda item: item.evidence_id,
    )
    _validate_unique_reconciliation_claims(reconciliations)

    claim_ids = {claim.claim_id for claim in claims}
    provenance_ids = {
        provenance.provenance_id for provenance in provenances
    }
    evidence_ids = {item.evidence_id for item in evidence}

    _validate_evidence(
        evidence=evidence,
        claim_ids=claim_ids,
        provenance_ids=provenance_ids,
    )

    _validate_claims(
        claims=claims,
        provenance_ids=provenance_ids,
    )

    _validate_reconciliations(
        reconciliations=reconciliations,
        claim_ids=claim_ids,
        evidence_ids=evidence_ids,
    )

    ordered_provenances = tuple(
        sorted(
            provenances,
            key=lambda item: item.provenance_id,
        )
    )

    ordered_evidence = tuple(
        sorted(
            evidence,
            key=lambda item: item.evidence_id,
        )
    )

    return EvidenceBundle(
        evidence_refs=tuple(
            item.evidence_id
            for item in ordered_evidence
        ),
        provenances=ordered_provenances,
        evidence=ordered_evidence,
    )


def _validate_unique_ids(
    *,
    objects: tuple[object, ...],
    object_name: str,
    object_id,
) -> None:
    ids = tuple(object_id(item) for item in objects)

    if len(ids) != len(set(ids)):
        raise EvidenceAssemblyError(
            f"duplicate {object_name} IDs are not allowed"
        )

    if any(
        not isinstance(identifier, str) or not identifier.strip()
        for identifier in ids
    ):
        raise EvidenceAssemblyError(
            f"{object_name} IDs must be non-empty strings"
        )


def _validate_unique_reconciliation_claims(
    reconciliations: tuple[ClaimReconciliation, ...],
) -> None:
    claim_ids = tuple(
        reconciliation.claim_id
        for reconciliation in reconciliations
    )

    if len(claim_ids) != len(set(claim_ids)):
        raise EvidenceAssemblyError(
            "duplicate reconciliation claim IDs are not allowed"
        )

    if any(
        not isinstance(claim_id, str) or not claim_id.strip()
        for claim_id in claim_ids
    ):
        raise EvidenceAssemblyError(
            "reconciliation claim IDs must be non-empty strings"
        )


def _validate_claims(
    *,
    claims: tuple[Claim, ...],
    provenance_ids: set[str],
) -> None:
    for claim in claims:
        _validate_reference_tuple(
            references=claim.provenance_refs,
            reference_type="claim provenance",
        )

        unknown = set(claim.provenance_refs) - provenance_ids

        if unknown:
            raise EvidenceAssemblyError(
                "claim references unknown provenance: "
                f"{sorted(unknown)}"
            )


def _validate_evidence(
    *,
    evidence: tuple[Evidence, ...],
    claim_ids: set[str],
    provenance_ids: set[str],
) -> None:
    for item in evidence:
        _validate_reference_tuple(
            references=item.provenance_refs,
            reference_type="evidence provenance",
        )

        unknown_provenance = (
            set(item.provenance_refs) - provenance_ids
        )

        if unknown_provenance:
            raise EvidenceAssemblyError(
                "evidence references unknown provenance: "
                f"{sorted(unknown_provenance)}"
            )

        if item.claim_id is not None:
            if not item.claim_id.strip():
                raise EvidenceAssemblyError(
                    "evidence claim_id must not be blank"
                )

            if item.claim_id not in claim_ids:
                raise EvidenceAssemblyError(
                    "evidence references unknown claim: "
                    f"{item.claim_id}"
                )


def _validate_reconciliations(
    *,
    reconciliations: tuple[ClaimReconciliation, ...],
    claim_ids: set[str],
    evidence_ids: set[str],
) -> None:
    for reconciliation in reconciliations:
        if reconciliation.claim_id not in claim_ids:
            raise EvidenceAssemblyError(
                "reconciliation references unknown claim: "
                f"{reconciliation.claim_id}"
            )

        _validate_reference_tuple(
            references=reconciliation.supporting_evidence_refs,
            reference_type="supporting evidence",
        )
        _validate_reference_tuple(
            references=reconciliation.contradicting_evidence_refs,
            reference_type="contradicting evidence",
        )

        supporting_unknown = (
            set(reconciliation.supporting_evidence_refs)
            - evidence_ids
        )

        if supporting_unknown:
            raise EvidenceAssemblyError(
                "reconciliation references unknown supporting evidence: "
                f"{sorted(supporting_unknown)}"
            )

        contradicting_unknown = (
            set(reconciliation.contradicting_evidence_refs)
            - evidence_ids
        )

        if contradicting_unknown:
            raise EvidenceAssemblyError(
                "reconciliation references unknown contradicting evidence: "
                f"{sorted(contradicting_unknown)}"
            )


def _validate_reference_tuple(
    *,
    references: tuple[str, ...],
    reference_type: str,
) -> None:
    if len(references) != len(set(references)):
        raise EvidenceAssemblyError(
            f"duplicate {reference_type} references are not allowed"
        )

    if any(
        not isinstance(reference, str) or not reference.strip()
        for reference in references
    ):
        raise EvidenceAssemblyError(
            f"{reference_type} references must be non-empty"
        )