from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
)
from vikat_hire.contracts.evaluation import DimensionEvaluation, ExperienceEvaluation
from vikat_hire.evaluation.dimensions import evaluate_dimension


class JDAlignedExperienceAggregationError(ValueError):
    """Raised when JD-aligned experience aggregation input is invalid."""


_ZERO = Decimal("0")
_QUANTUM = Decimal("0.01")


def aggregate_jd_aligned_experience(
    *,
    requirement_ids: tuple[str, ...],
    evaluations: tuple[ExperienceEvaluation, ...],
) -> DimensionEvaluation:
    """Aggregate per-requirement experience results without applying weights."""
    if not isinstance(requirement_ids, tuple) or any(
        not isinstance(item, str) or not item.strip() for item in requirement_ids
    ):
        raise JDAlignedExperienceAggregationError(
            "requirement_ids must be a tuple of non-blank strings"
        )
    if len(requirement_ids) != len(set(requirement_ids)):
        raise JDAlignedExperienceAggregationError(
            "duplicate known experience requirement IDs are not allowed"
        )
    if not isinstance(evaluations, tuple) or any(
        not isinstance(item, ExperienceEvaluation) for item in evaluations
    ):
        raise JDAlignedExperienceAggregationError(
            "evaluations must be a tuple of ExperienceEvaluation objects"
        )

    known_requirements = set(requirement_ids)
    seen_requirements: set[str] = set()
    evaluated_values: list[Decimal] = []
    evidence_refs: list[str] = []
    provenance_refs: list[str] = []
    evaluated_requirement_refs: list[str] = []

    for evaluation in evaluations:
        requirement_id = evaluation.requirement_id
        if not requirement_id.strip():
            raise JDAlignedExperienceAggregationError(
                "experience evaluation requirement_id must not be blank"
            )
        if requirement_id not in known_requirements:
            raise JDAlignedExperienceAggregationError(
                "experience evaluation references unknown requirement: "
                f"{requirement_id}"
            )
        if requirement_id in seen_requirements:
            raise JDAlignedExperienceAggregationError(
                "duplicate experience evaluation requirement_id: "
                f"{requirement_id}"
            )
        _validate_references(evaluation)
        seen_requirements.add(requirement_id)
        evidence_refs.extend(evaluation.evidence_refs)
        provenance_refs.extend(evaluation.provenance_refs)

        if evaluation.resolution is DimensionResolution.EVALUATED:
            value = evaluation.raw_value
            if not isinstance(value, Decimal) or not value.is_finite():
                raise JDAlignedExperienceAggregationError(
                    f"evaluated experience {requirement_id!r} requires a finite Decimal raw_value"
                )
            evaluated_values.append(value)
            evaluated_requirement_refs.append(requirement_id)
        elif evaluation.resolution is not DimensionResolution.EXCLUDED:
            raise JDAlignedExperienceAggregationError(
                f"unsupported experience resolution: {evaluation.resolution!r}"
            )

    dimension_requirement_refs = tuple(
        evaluation.requirement_id for evaluation in evaluations
    )
    deduped_evidence_refs = tuple(dict.fromkeys(evidence_refs))
    deduped_provenance_refs = tuple(dict.fromkeys(provenance_refs))

    if not evaluated_values:
        return evaluate_dimension(
            dimension=DimensionName.JD_ALIGNED_EXPERIENCE,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EXCLUDED,
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
            evidence_refs=deduped_evidence_refs,
            requirement_refs=dimension_requirement_refs,
            provenance_refs=deduped_provenance_refs,
            rationale="No JD-aligned experience requirements were evaluable.",
        )

    raw_value = (
        sum(evaluated_values, _ZERO) / Decimal(len(evaluated_values))
    ).quantize(_QUANTUM, rounding=ROUND_HALF_UP)

    return evaluate_dimension(
        dimension=DimensionName.JD_ALIGNED_EXPERIENCE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=raw_value,
        evidence_refs=deduped_evidence_refs,
        requirement_refs=dimension_requirement_refs,
        provenance_refs=deduped_provenance_refs,
        rationale=(
            f"Arithmetic mean of {len(evaluated_values)} evaluated JD-aligned "
            "experience requirements."
        ),
    )


def _validate_references(evaluation: ExperienceEvaluation) -> None:
    for name, refs in (
        ("evidence", evaluation.evidence_refs),
        ("provenance", evaluation.provenance_refs),
    ):
        if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            raise JDAlignedExperienceAggregationError(
                f"experience evaluation {name} references must be non-blank strings"
            )
        if len(refs) != len(set(refs)):
            raise JDAlignedExperienceAggregationError(
                f"experience evaluation contains duplicate {name} references"
            )
