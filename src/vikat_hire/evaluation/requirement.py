from __future__ import annotations

from decimal import Decimal

from vikat_hire.contracts.common import MatchStatus
from vikat_hire.contracts.evaluation import RequirementEvaluation
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.matching import KeywordMatch


class RequirementEvaluationError(ValueError):
    """Raised when requirement evaluation input is invalid."""


def evaluate_requirement(
    *,
    requirement_id: str,
    matches: tuple[KeywordMatch, ...],
    candidate_claims: tuple[Claim, ...],
) -> RequirementEvaluation:
    """
    Deterministically evaluate one JD requirement.

    This module intentionally evaluates only evidence supplied to it.
    It does not search external systems and does not invoke an LLM.

    Match precedence:

        MATCHED
        PARTIAL
        NOT_MATCHED
        UNRESOLVED

    A requirement with no usable evidence is UNRESOLVED rather than
    automatically receiving a zero score.
    """

    _validate_inputs(
        requirement_id=requirement_id,
        matches=matches,
        candidate_claims=candidate_claims,
    )

    relevant_matches = tuple(
        match
        for match in matches
        if match.requirement_id == requirement_id
    )

    if not relevant_matches:
        return RequirementEvaluation(
            requirement_id=requirement_id,
            status=MatchStatus.UNRESOLVED,
            raw_score=Decimal("0"),
            evidence_refs=(),
            provenance_refs=(),
            rationale="No candidate evidence was available.",
        )

    strongest = max(
        relevant_matches,
        key=lambda match: match.score,
    )

    evidence_refs = tuple(
        sorted(
            {
                *strongest.provenance_refs,
                *(
                    claim_ref
                    for claim_ref in _claim_provenance_refs(
                        candidate_claims=candidate_claims,
                        claim_id=strongest.candidate_claim_id,
                    )
                ),
            }
        )
    )

    status = _status_from_match(strongest.status)

    return RequirementEvaluation(
        requirement_id=requirement_id,
        status=status,
        raw_score=_raw_score_for_status(
            status=status,
            match_score=strongest.score,
        ),
        evidence_refs=evidence_refs,
        provenance_refs=strongest.provenance_refs,
        rationale=_rationale_for_status(status=status),
    )


def _validate_inputs(
    *,
    requirement_id: str,
    matches: tuple[KeywordMatch, ...],
    candidate_claims: tuple[Claim, ...],
) -> None:
    if not requirement_id.strip():
        raise RequirementEvaluationError(
            "requirement_id must not be blank"
        )

    claim_ids = {
        claim.claim_id
        for claim in candidate_claims
    }

    for match in matches:
        if match.requirement_id != requirement_id:
            continue

        if (
            match.candidate_claim_id is not None
            and match.candidate_claim_id not in claim_ids
        ):
            raise RequirementEvaluationError(
                "keyword match references unknown candidate claim: "
                f"{match.candidate_claim_id}"
            )


def _claim_provenance_refs(
    *,
    candidate_claims: tuple[Claim, ...],
    claim_id: str | None,
) -> tuple[str, ...]:
    if claim_id is None:
        return ()

    for claim in candidate_claims:
        if claim.claim_id == claim_id:
            return claim.provenance_refs

    return ()


def _status_from_match(status: MatchStatus) -> MatchStatus:
    if status is MatchStatus.MATCHED:
        return MatchStatus.MATCHED

    if status is MatchStatus.PARTIAL:
        return MatchStatus.PARTIAL

    if status is MatchStatus.NOT_MATCHED:
        return MatchStatus.NOT_MATCHED

    return MatchStatus.UNRESOLVED


def _raw_score_for_status(
    *,
    status: MatchStatus,
    match_score: Decimal,
) -> Decimal:
    if status is MatchStatus.MATCHED:
        return match_score

    if status is MatchStatus.PARTIAL:
        return match_score

    if status is MatchStatus.NOT_MATCHED:
        return Decimal("0")

    # UNRESOLVED is deliberately not represented as a negative score.
    return Decimal("0")


def _rationale_for_status(
    *,
    status: MatchStatus,
) -> str:
    rationales = {
        MatchStatus.MATCHED: (
            "Deterministic evidence matched the requirement."
        ),
        MatchStatus.PARTIAL: (
            "Deterministic evidence partially matched the requirement."
        ),
        MatchStatus.NOT_MATCHED: (
            "Available deterministic evidence did not match the requirement."
        ),
        MatchStatus.UNRESOLVED: (
            "The requirement could not be resolved from available evidence."
        ),
    }

    return rationales[status]