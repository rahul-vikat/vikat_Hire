from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    MatchStatus,
)
from vikat_hire.contracts.evaluation import DimensionEvaluation
from vikat_hire.contracts.matching import SemanticMatch
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.evaluation.dimensions import evaluate_dimension


class SemanticFitAggregationError(ValueError):
    """Raised when deterministic semantic-fit aggregation input is invalid."""


_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_QUANTUM = Decimal("0.01")


def aggregate_semantic_fit(
    *,
    requirements: tuple[JDRequirement, ...],
    matches: tuple[SemanticMatch, ...],
) -> DimensionEvaluation:
    """Aggregate deterministic semantic matches into the SEMANTIC_FIT dimension.

    The input is deterministic ``SemanticMatch`` data only. LLM proposals,
    screening weights, and final-score calculations are deliberately absent.
    A requirement with no supplied match is not fabricated into an evaluation.
    """
    if not isinstance(requirements, tuple) or any(
        not isinstance(item, JDRequirement) for item in requirements
    ):
        raise SemanticFitAggregationError(
            "requirements must be a tuple of JDRequirement objects"
        )
    if not isinstance(matches, tuple) or any(
        not isinstance(item, SemanticMatch) for item in matches
    ):
        raise SemanticFitAggregationError(
            "matches must be a tuple of SemanticMatch objects"
        )

    requirement_by_id: dict[str, JDRequirement] = {}
    for requirement in requirements:
        requirement_id = requirement.requirement_id
        if not requirement_id.strip():
            raise SemanticFitAggregationError("requirement IDs must not be blank")
        if requirement_id in requirement_by_id:
            raise SemanticFitAggregationError(
                f"duplicate requirement ID: {requirement_id}"
            )
        _validate_references(
            label=f"requirement {requirement_id!r}",
            evidence_refs=requirement.evidence_refs,
            provenance_refs=requirement.provenance_refs,
        )
        requirement_by_id[requirement_id] = requirement

    seen_requirements: set[str] = set()
    seen_match_ids: set[str] = set()
    evaluable_scores: list[Decimal] = []
    requirement_refs: list[str] = []
    evidence_refs: list[str] = []
    provenance_refs: list[str] = []

    for match in matches:
        if not match.requirement_id.strip():
            raise SemanticFitAggregationError(
                "semantic match requirement_id must not be blank"
            )
        if match.requirement_id not in requirement_by_id:
            raise SemanticFitAggregationError(
                "semantic match references unknown requirement: "
                f"{match.requirement_id}"
            )
        if match.requirement_id in seen_requirements:
            raise SemanticFitAggregationError(
                "duplicate semantic match requirement_id: "
                f"{match.requirement_id}"
            )
        if not match.match_id.strip() or match.match_id in seen_match_ids:
            raise SemanticFitAggregationError(
                "semantic match IDs must be non-blank and unique"
            )
        _validate_references(
            label=f"semantic match {match.match_id!r}",
            evidence_refs=(),
            provenance_refs=match.provenance_refs,
        )
        if not isinstance(match.score, Decimal) or not match.score.is_finite():
            raise SemanticFitAggregationError(
                f"semantic match {match.match_id!r} score must be a finite Decimal"
            )
        if match.score < _ZERO or match.score > _HUNDRED:
            raise SemanticFitAggregationError(
                f"semantic match {match.match_id!r} score must be between 0 and 100"
            )

        seen_requirements.add(match.requirement_id)
        seen_match_ids.add(match.match_id)
        requirement_refs.append(match.requirement_id)
        requirement = requirement_by_id[match.requirement_id]
        evidence_refs.extend(requirement.evidence_refs)
        provenance_refs.extend(requirement.provenance_refs)
        provenance_refs.extend(match.provenance_refs)

        if match.status in {MatchStatus.MATCHED, MatchStatus.PARTIAL}:
            evaluable_scores.append(match.score)
        elif match.status is MatchStatus.NOT_MATCHED:
            evaluable_scores.append(_ZERO)
        elif match.status is not MatchStatus.UNRESOLVED:
            raise SemanticFitAggregationError(
                f"unsupported semantic match status: {match.status!r}"
            )

    deduped_evidence_refs = _ordered_unique(evidence_refs)
    deduped_provenance_refs = _ordered_unique(provenance_refs)
    deduped_requirement_refs = _ordered_unique(requirement_refs)

    if not evaluable_scores:
        return evaluate_dimension(
            dimension=DimensionName.SEMANTIC_FIT,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EXCLUDED,
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
            evidence_refs=deduped_evidence_refs,
            requirement_refs=deduped_requirement_refs,
            provenance_refs=deduped_provenance_refs,
            rationale="No semantic requirements had evaluable deterministic matches.",
        )

    raw_value = (
        sum(evaluable_scores, _ZERO) / Decimal(len(evaluable_scores))
    ).quantize(_QUANTUM, rounding=ROUND_HALF_UP)

    return evaluate_dimension(
        dimension=DimensionName.SEMANTIC_FIT,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=raw_value,
        evidence_refs=deduped_evidence_refs,
        requirement_refs=deduped_requirement_refs,
        provenance_refs=deduped_provenance_refs,
        rationale=(
            f"Arithmetic mean of {len(evaluable_scores)} evaluable deterministic "
            "semantic requirement scores."
        ),
    )


def _validate_references(
    *,
    label: str,
    evidence_refs: tuple[str, ...],
    provenance_refs: tuple[str, ...],
) -> None:
    for name, refs in (
        ("evidence", evidence_refs),
        ("provenance", provenance_refs),
    ):
        if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            raise SemanticFitAggregationError(
                f"{label} {name} references must be non-blank strings"
            )
        if len(refs) != len(set(refs)):
            raise SemanticFitAggregationError(
                f"{label} contains duplicate {name} references"
            )


def _ordered_unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
