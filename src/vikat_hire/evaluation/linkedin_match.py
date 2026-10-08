from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    EvidenceStatus,
    ExclusionReason,
    ContradictionStatus,
)
from vikat_hire.contracts.evidence import (
    Claim,
    ClaimReconciliation,
    Evidence,
    Provenance,
)
from vikat_hire.contracts.evaluation import DimensionEvaluation

from .dimensions import evaluate_dimension


class LinkedInEvaluationError(ValueError):
    """Raised when LinkedIn evidence evaluation input is invalid."""


_EXCLUDED_EVIDENCE_STATUSES = {
    EvidenceStatus.NOT_FOUND,
    EvidenceStatus.NOT_AUTHORIZED,
    EvidenceStatus.UNAVAILABLE,
    EvidenceStatus.NOT_APPLICABLE,
}


def evaluate_linkedin_evidence(
    *,
    claims: tuple[Claim, ...],
    evidence: tuple[Evidence, ...],
    provenances: tuple[Provenance, ...],
    reconciliations: tuple[ClaimReconciliation, ...],
) -> DimensionEvaluation:
    """
    Deterministically evaluate LinkedIn corroboration of candidate claims.

    Authoritative rule:

        score =
            corroborated claims
            -------------------
            eligible non-contradicted claims
            * 100

    A claim is corroborated when LinkedIn provides SUPPORTED evidence.

    PARTIALLY_SUPPORTED evidence is eligible but does not count as
    corroboration.

    Validated or suspected contradictions are handled separately and are
    excluded from the score denominator. They remain available to the
    downstream evaluation/policy layer through the claim/evidence references.

    NOT_FOUND, NOT_AUTHORIZED, UNAVAILABLE, and NOT_APPLICABLE evidence is
    excluded from the denominator.

    If no eligible non-contradicted claims remain, the dimension is excluded
    rather than assigned a score of zero.

    This function does not apply the configured scoring weight.
    """

    _validate_unique_ids(
        claims=claims,
        evidence=evidence,
        provenances=provenances,
    )
    _validate_references(
        claims=claims,
        evidence=evidence,
        provenances=provenances,
        reconciliations=reconciliations,
    )

    linkedin_provenance_ids = {
        provenance.provenance_id
        for provenance in provenances
        if provenance.source_type.value == "linkedin"
    }

    if not linkedin_provenance_ids:
        return evaluate_dimension(
            dimension=DimensionName.LINKEDIN_EVIDENCE,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EXCLUDED,
            exclusion_reason=ExclusionReason.NOT_FOUND,
            rationale=(
                "LinkedIn evidence was not available for candidate claims."
            ),
        )

    linkedin_evidence = tuple(
        item
        for item in evidence
        if linkedin_provenance_ids.intersection(item.provenance_refs)
        and item.claim_id is not None
    )

    claim_by_id = {
        claim.claim_id: claim
        for claim in claims
    }

    reconciliation_by_claim = {
        reconciliation.claim_id: reconciliation
        for reconciliation in reconciliations
    }

    corroborated_claim_ids: list[str] = []
    eligible_claim_ids: list[str] = []
    excluded_claim_ids: list[str] = []
    contradiction_claim_ids: list[str] = []

    evidence_refs: set[str] = set()
    provenance_refs: set[str] = set()

    evidence_by_claim: dict[str, list[Evidence]] = {}

    for item in linkedin_evidence:
        assert item.claim_id is not None
        evidence_by_claim.setdefault(item.claim_id, []).append(item)

    for claim in sorted(
        claims,
        key=lambda item: item.claim_id,
    ):
        claim_evidence = evidence_by_claim.get(claim.claim_id, [])

        if not claim_evidence:
            excluded_claim_ids.append(claim.claim_id)
            continue

        reconciliation = reconciliation_by_claim.get(claim.claim_id)

        if reconciliation is not None and (
            reconciliation.contradiction_status
            in {
                ContradictionStatus.SUSPECTED,
                ContradictionStatus.VALIDATED,
            }
        ):
            contradiction_claim_ids.append(claim.claim_id)

            evidence_refs.update(
                reconciliation.contradicting_evidence_refs
            )
            provenance_refs.update(
                provenance_ref
                for item in claim_evidence
                for provenance_ref in item.provenance_refs
            )
            continue

        usable_evidence = tuple(
            item
            for item in claim_evidence
            if item.status not in _EXCLUDED_EVIDENCE_STATUSES
        )

        if not usable_evidence:
            excluded_claim_ids.append(claim.claim_id)
            continue

        eligible_claim_ids.append(claim.claim_id)

        evidence_refs.update(
            item.evidence_id
            for item in usable_evidence
        )
        provenance_refs.update(
            provenance_ref
            for item in usable_evidence
            for provenance_ref in item.provenance_refs
        )

        if any(
            item.status is EvidenceStatus.SUPPORTED
            for item in usable_evidence
        ):
            corroborated_claim_ids.append(claim.claim_id)

    if not eligible_claim_ids:
        reason = (
            ExclusionReason.INSUFFICIENT_EVIDENCE
            if contradiction_claim_ids
            or excluded_claim_ids
            else ExclusionReason.NOT_FOUND
        )

        return evaluate_dimension(
            dimension=DimensionName.LINKEDIN_EVIDENCE,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EXCLUDED,
            exclusion_reason=reason,
            evidence_refs=tuple(sorted(evidence_refs)),
            requirement_refs=tuple(
                sorted(
                    claim_by_id[claim_id].claim_id
                    for claim_id in claim_by_id
                    if claim_id in excluded_claim_ids
                )
            ),
            provenance_refs=tuple(sorted(provenance_refs)),
            rationale=_build_excluded_rationale(
                contradiction_count=len(contradiction_claim_ids),
                excluded_count=len(excluded_claim_ids),
            ),
        )

    eligible_count = Decimal(len(eligible_claim_ids))
    corroborated_count = Decimal(len(corroborated_claim_ids))

    raw_value = (
        corroborated_count
        / eligible_count
        * Decimal("100")
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return evaluate_dimension(
        dimension=DimensionName.LINKEDIN_EVIDENCE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=raw_value,
        evidence_refs=tuple(sorted(evidence_refs)),
        requirement_refs=tuple(sorted(eligible_claim_ids)),
        provenance_refs=tuple(sorted(provenance_refs)),
        rationale=(
            f"LinkedIn corroborated {len(corroborated_claim_ids)} of "
            f"{len(eligible_claim_ids)} eligible non-contradicted candidate "
            f"claims ({raw_value}%). "
            f"{len(contradiction_claim_ids)} claim(s) were handled as "
            "contradictions separately and excluded from the percentage. "
            f"{len(excluded_claim_ids)} claim(s) had unresolved or "
            "unavailable LinkedIn evidence and were excluded."
        ),
    )


def _validate_unique_ids(
    *,
    claims: tuple[Claim, ...],
    evidence: tuple[Evidence, ...],
    provenances: tuple[Provenance, ...],
) -> None:
    claim_ids = tuple(item.claim_id for item in claims)
    evidence_ids = tuple(item.evidence_id for item in evidence)
    provenance_ids = tuple(item.provenance_id for item in provenances)

    if len(claim_ids) != len(set(claim_ids)):
        raise LinkedInEvaluationError(
            "duplicate candidate claim IDs are not allowed"
        )

    if len(evidence_ids) != len(set(evidence_ids)):
        raise LinkedInEvaluationError(
            "duplicate evidence IDs are not allowed"
        )

    if len(provenance_ids) != len(set(provenance_ids)):
        raise LinkedInEvaluationError(
            "duplicate provenance IDs are not allowed"
        )


def _validate_references(
    *,
    claims: tuple[Claim, ...],
    evidence: tuple[Evidence, ...],
    provenances: tuple[Provenance, ...],
    reconciliations: tuple[ClaimReconciliation, ...],
) -> None:
    claim_ids = {item.claim_id for item in claims}
    evidence_ids = {item.evidence_id for item in evidence}
    provenance_ids = {item.provenance_id for item in provenances}

    for item in claims:
        unknown = set(item.provenance_refs) - provenance_ids

        if unknown:
            raise LinkedInEvaluationError(
                "candidate claim references unknown provenance: "
                f"{sorted(unknown)}"
            )

    for item in evidence:
        unknown_provenance = (
            set(item.provenance_refs) - provenance_ids
        )

        if unknown_provenance:
            raise LinkedInEvaluationError(
                "LinkedIn evidence references unknown provenance: "
                f"{sorted(unknown_provenance)}"
            )

        if item.claim_id is not None and item.claim_id not in claim_ids:
            raise LinkedInEvaluationError(
                "evidence references unknown candidate claim: "
                f"{item.claim_id}"
            )

    seen_reconciliation_claims: set[str] = set()

    for reconciliation in reconciliations:
        if reconciliation.claim_id not in claim_ids:
            raise LinkedInEvaluationError(
                "reconciliation references unknown candidate claim: "
                f"{reconciliation.claim_id}"
            )

        if reconciliation.claim_id in seen_reconciliation_claims:
            raise LinkedInEvaluationError(
                "duplicate reconciliation claim IDs are not allowed"
            )

        seen_reconciliation_claims.add(reconciliation.claim_id)

        unknown_supporting = (
            set(reconciliation.supporting_evidence_refs)
            - evidence_ids
        )

        if unknown_supporting:
            raise LinkedInEvaluationError(
                "reconciliation references unknown supporting evidence: "
                f"{sorted(unknown_supporting)}"
            )

        unknown_contradicting = (
            set(reconciliation.contradicting_evidence_refs)
            - evidence_ids
        )

        if unknown_contradicting:
            raise LinkedInEvaluationError(
                "reconciliation references unknown contradicting evidence: "
                f"{sorted(unknown_contradicting)}"
            )


def _build_excluded_rationale(
    *,
    contradiction_count: int,
    excluded_count: int,
) -> str:
    return (
        "LinkedIn evidence dimension was excluded because no candidate "
        "claims had usable non-contradicted LinkedIn evidence. "
        f"{contradiction_count} claim(s) were handled as contradictions "
        f"separately and {excluded_count} claim(s) had unresolved or "
        "unavailable evidence."
    )