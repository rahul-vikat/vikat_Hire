from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
)
from vikat_hire.contracts.evaluation import (
    DimensionEvaluation,
    EvaluationResult,
)


class DimensionEvaluationError(ValueError):
    """Raised when dimension evaluation input violates domain invariants."""


def evaluate_dimension(
    *,
    dimension: DimensionName,
    applicability: ApplicabilityStatus,
    resolution: DimensionResolution,
    raw_value: Decimal | None = None,
    exclusion_reason: ExclusionReason | None = None,
    evidence_refs: tuple[str, ...] = (),
    requirement_refs: tuple[str, ...] = (),
    provenance_refs: tuple[str, ...] = (),
    rationale: str,
) -> DimensionEvaluation:
    """
    Normalize one already-evaluated deterministic dimension.

    This function does not calculate the candidate score and does not apply
    scoring weights. Numeric values must already have been produced by the
    authoritative deterministic evaluator for that dimension.

    Applicability answers:
        "Should this dimension participate for this screening?"

    Resolution answers:
        "Was this applicable dimension successfully evaluated?"

    Therefore an applicable dimension may still be excluded when evidence is
    insufficient, unavailable, unauthorized, or otherwise unresolved.
    """

    _validate_references(
        evidence_refs=evidence_refs,
        requirement_refs=requirement_refs,
        provenance_refs=provenance_refs,
    )

    if not rationale.strip():
        raise DimensionEvaluationError(
            "dimension rationale must not be blank"
        )

    if (
        applicability is ApplicabilityStatus.NOT_APPLICABLE
        and resolution is DimensionResolution.EVALUATED
    ):
        raise DimensionEvaluationError(
            "not_applicable dimension cannot be evaluated"
        )

    if resolution is DimensionResolution.EVALUATED:
        if raw_value is None:
            raise DimensionEvaluationError(
                "evaluated dimension requires raw_value"
            )

        if exclusion_reason is not None:
            raise DimensionEvaluationError(
                "evaluated dimension cannot have exclusion_reason"
            )

    elif resolution is DimensionResolution.EXCLUDED:
        if raw_value is not None:
            raise DimensionEvaluationError(
                "excluded dimension cannot have raw_value"
            )

        if exclusion_reason is None:
            raise DimensionEvaluationError(
                "excluded dimension requires exclusion_reason"
            )

    else:
        raise DimensionEvaluationError(
            f"unsupported dimension resolution: {resolution!r}"
        )

    return DimensionEvaluation(
        dimension=dimension,
        applicability=applicability,
        resolution=resolution,
        raw_value=raw_value,
        exclusion_reason=exclusion_reason,
        evidence_refs=evidence_refs,
        requirement_refs=requirement_refs,
        provenance_refs=provenance_refs,
        rationale=rationale,
    )


def assemble_evaluation_result(
    *,
    screening_id: str,
    dimensions: Iterable[DimensionEvaluation],
    contradiction_refs: tuple[str, ...] = (),
) -> EvaluationResult:
    """
    Assemble the authoritative dimension-evaluation result.

    This function only validates and deterministically orders already-produced
    dimension evaluations. It never recalculates their values.
    """

    if not screening_id.strip():
        raise DimensionEvaluationError(
            "screening_id must not be blank"
        )

    dimension_tuple = tuple(dimensions)

    seen: set[DimensionName] = set()

    for evaluation in dimension_tuple:
        if evaluation.dimension in seen:
            raise DimensionEvaluationError(
                "duplicate dimension evaluation is not allowed: "
                f"{evaluation.dimension.value}"
            )

        seen.add(evaluation.dimension)

        _validate_dimension_consistency(evaluation)

    if len(contradiction_refs) != len(set(contradiction_refs)):
        raise DimensionEvaluationError(
            "duplicate contradiction references are not allowed"
        )

    if any(
        not reference.strip()
        for reference in contradiction_refs
    ):
        raise DimensionEvaluationError(
            "contradiction references must be non-empty"
        )

    ordered_dimensions = tuple(
        sorted(
            dimension_tuple,
            key=lambda evaluation: evaluation.dimension.value,
        )
    )

    return EvaluationResult(
        screening_id=screening_id,
        dimensions=ordered_dimensions,
        contradiction_refs=contradiction_refs,
        deterministic=True,
    )


def _validate_dimension_consistency(
    evaluation: DimensionEvaluation,
) -> None:
    """
    Validate invariants that are stronger than the base Pydantic contract.

    The DimensionEvaluation contract intentionally remains a general data
    contract. These rules belong to the deterministic evaluation boundary.
    """

    if (
        evaluation.applicability is ApplicabilityStatus.NOT_APPLICABLE
        and evaluation.resolution is DimensionResolution.EVALUATED
    ):
        raise DimensionEvaluationError(
            "not_applicable dimension cannot be evaluated: "
            f"{evaluation.dimension.value}"
        )

    if evaluation.resolution is DimensionResolution.EVALUATED:
        if evaluation.raw_value is None:
            raise DimensionEvaluationError(
                "evaluated dimension requires raw_value: "
                f"{evaluation.dimension.value}"
            )

        if evaluation.exclusion_reason is not None:
            raise DimensionEvaluationError(
                "evaluated dimension cannot have exclusion_reason: "
                f"{evaluation.dimension.value}"
            )

        return

    if evaluation.resolution is DimensionResolution.EXCLUDED:
        if evaluation.raw_value is not None:
            raise DimensionEvaluationError(
                "excluded dimension cannot have raw_value: "
                f"{evaluation.dimension.value}"
            )

        if evaluation.exclusion_reason is None:
            raise DimensionEvaluationError(
                "excluded dimension requires exclusion_reason: "
                f"{evaluation.dimension.value}"
            )

        return

    raise DimensionEvaluationError(
        f"unsupported dimension resolution: {evaluation.resolution!r}"
    )


def _validate_references(
    *,
    evidence_refs: tuple[str, ...],
    requirement_refs: tuple[str, ...],
    provenance_refs: tuple[str, ...],
) -> None:
    for reference_type, references in (
        ("evidence", evidence_refs),
        ("requirement", requirement_refs),
        ("provenance", provenance_refs),
    ):
        if len(references) != len(set(references)):
            raise DimensionEvaluationError(
                f"duplicate {reference_type} references are not allowed"
            )

        if any(not reference.strip() for reference in references):
            raise DimensionEvaluationError(
                f"{reference_type} references must be non-empty"
            )