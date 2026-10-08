from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    MatchStatus,
    SourceType,
)
from vikat_hire.contracts.evidence import Claim, Provenance
from vikat_hire.contracts.evaluation import DimensionEvaluation
from vikat_hire.contracts.matching import KeywordMatch

from .dimensions import evaluate_dimension


class GitHubEvaluationError(ValueError):
    """Raised when GitHub evidence evaluation input is invalid."""


def evaluate_github_evidence(
    *,
    requirements: tuple,
    claims: tuple[Claim, ...],
    matches: tuple[KeywordMatch, ...],
    provenances: tuple[Provenance, ...],
) -> DimensionEvaluation:
    """
    Deterministically evaluate GitHub evidence against JD requirements.

    Authoritative rule:

        GitHub raw score =
            sum of evaluated requirement scores
            --------------------------------
            number of evaluated requirements

    Requirement scoring:

        MATCHED      -> supplied deterministic match score
        PARTIAL      -> supplied deterministic match score
        NOT_MATCHED  -> 0
        UNRESOLVED   -> excluded from denominator

    Only evidence originating from GitHub is considered.

    This function does not apply the configured 5% scoring weight.
    """

    _validate_inputs(
        requirements=requirements,
        claims=claims,
        matches=matches,
        provenances=provenances,
    )

    github_provenance_ids = {
        provenance.provenance_id
        for provenance in provenances
        if provenance.source_type is SourceType.GITHUB
    }

    if not github_provenance_ids:
        return evaluate_dimension(
            dimension=DimensionName.GITHUB_EVIDENCE,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EXCLUDED,
            exclusion_reason=ExclusionReason.NOT_FOUND,
            rationale=(
                "GitHub evidence was not available for JD requirements."
            ),
        )

    claim_by_id = {
        claim.claim_id: claim
        for claim in claims
    }

    github_matches = tuple(
        match
        for match in matches
        if github_provenance_ids.intersection(match.provenance_refs)
    )

    evaluated_scores: list[Decimal] = []
    evaluated_requirement_ids: list[str] = []
    unresolved_requirement_ids: list[str] = []

    evidence_refs: set[str] = set()
    provenance_refs: set[str] = set()

    for requirement in sorted(
        requirements,
        key=lambda item: item.requirement_id,
    ):
        requirement_matches = tuple(
            match
            for match in github_matches
            if match.requirement_id == requirement.requirement_id
        )

        if not requirement_matches:
            unresolved_requirement_ids.append(
                requirement.requirement_id
            )
            continue

        strongest = max(
            requirement_matches,
            key=lambda match: (
                match.score,
                _match_status_priority(match.status),
                match.match_id,
            ),
        )

        if strongest.status is MatchStatus.UNRESOLVED:
            unresolved_requirement_ids.append(
                requirement.requirement_id
            )
            continue

        evaluated_requirement_ids.append(
            requirement.requirement_id
        )

        score = _score_for_match(strongest)

        evaluated_scores.append(score)

        evidence_refs.update(
            strongest.provenance_refs
        )

        if strongest.candidate_claim_id is not None:
            claim = claim_by_id.get(strongest.candidate_claim_id)

            if claim is not None:
                evidence_refs.update(claim.provenance_refs)

        provenance_refs.update(
            strongest.provenance_refs
        )

    if not evaluated_scores:
        return evaluate_dimension(
            dimension=DimensionName.GITHUB_EVIDENCE,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EXCLUDED,
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
            evidence_refs=tuple(sorted(evidence_refs)),
            requirement_refs=tuple(
                sorted(unresolved_requirement_ids)
            ),
            provenance_refs=tuple(sorted(provenance_refs)),
            rationale=(
                "GitHub evidence dimension was excluded because no JD "
                "requirements could be deterministically evaluated from "
                "available GitHub evidence."
            ),
        )

    raw_value = (
        sum(evaluated_scores, Decimal("0"))
        / Decimal(len(evaluated_scores))
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return evaluate_dimension(
        dimension=DimensionName.GITHUB_EVIDENCE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=raw_value,
        evidence_refs=tuple(sorted(evidence_refs)),
        requirement_refs=tuple(sorted(evaluated_requirement_ids)),
        provenance_refs=tuple(sorted(provenance_refs)),
        rationale=(
            f"GitHub evidence evaluated {len(evaluated_scores)} JD "
            f"requirement(s) with a deterministic suitability score of "
            f"{raw_value}%. "
            f"{len(unresolved_requirement_ids)} requirement(s) were "
            "unresolved and excluded from the denominator."
        ),
    )


def _score_for_match(match: KeywordMatch) -> Decimal:
    if match.status is MatchStatus.MATCHED:
        return match.score

    if match.status is MatchStatus.PARTIAL:
        return match.score

    if match.status is MatchStatus.NOT_MATCHED:
        return Decimal("0")

    return Decimal("0")


def _match_status_priority(status: MatchStatus) -> int:
    return {
        MatchStatus.MATCHED: 4,
        MatchStatus.PARTIAL: 3,
        MatchStatus.NOT_MATCHED: 2,
        MatchStatus.UNRESOLVED: 1,
    }[status]


def _validate_inputs(
    *,
    requirements: tuple,
    claims: tuple[Claim, ...],
    matches: tuple[KeywordMatch, ...],
    provenances: tuple[Provenance, ...],
) -> None:
    requirement_ids = tuple(
        requirement.requirement_id
        for requirement in requirements
    )

    if len(requirement_ids) != len(set(requirement_ids)):
        raise GitHubEvaluationError(
            "duplicate JD requirement IDs are not allowed"
        )

    claim_ids = tuple(
        claim.claim_id
        for claim in claims
    )

    if len(claim_ids) != len(set(claim_ids)):
        raise GitHubEvaluationError(
            "duplicate candidate claim IDs are not allowed"
        )

    match_ids = tuple(
        match.match_id
        for match in matches
    )

    if len(match_ids) != len(set(match_ids)):
        raise GitHubEvaluationError(
            "duplicate keyword match IDs are not allowed"
        )

    provenance_ids = tuple(
        provenance.provenance_id
        for provenance in provenances
    )

    if len(provenance_ids) != len(set(provenance_ids)):
        raise GitHubEvaluationError(
            "duplicate provenance IDs are not allowed"
        )

    known_requirements = set(requirement_ids)
    known_claims = set(claim_ids)
    known_provenances = set(provenance_ids)

    for match in matches:
        if match.requirement_id not in known_requirements:
            raise GitHubEvaluationError(
                "GitHub match references unknown JD requirement: "
                f"{match.requirement_id}"
            )

        if (
            match.candidate_claim_id is not None
            and match.candidate_claim_id not in known_claims
        ):
            raise GitHubEvaluationError(
                "GitHub match references unknown candidate claim: "
                f"{match.candidate_claim_id}"
            )

        unknown_provenances = (
            set(match.provenance_refs) - known_provenances
        )

        if unknown_provenances:
            raise GitHubEvaluationError(
                "GitHub match references unknown provenance: "
                f"{sorted(unknown_provenances)}"
            )

    for claim in claims:
        unknown_provenances = (
            set(claim.provenance_refs) - known_provenances
        )

        if unknown_provenances:
            raise GitHubEvaluationError(
                "candidate claim references unknown provenance: "
                f"{sorted(unknown_provenances)}"
            )