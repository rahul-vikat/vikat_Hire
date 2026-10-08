from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    DimensionName,
    DimensionResolution,
    ExclusionReason,
)
from vikat_hire.contracts.evaluation import ExperienceEvaluation
from vikat_hire.evaluation.jd_aligned_experience import (
    JDAlignedExperienceAggregationError,
    aggregate_jd_aligned_experience,
)


def _evaluation(
    requirement_id: str,
    *,
    raw_value: str | None,
    evidence_refs: tuple[str, ...] = (),
    provenance_refs: tuple[str, ...] = (),
) -> ExperienceEvaluation:
    excluded = raw_value is None
    return ExperienceEvaluation(
        requirement_id=requirement_id,
        resolution=(DimensionResolution.EXCLUDED if excluded else DimensionResolution.EVALUATED),
        aligned_months=0 if excluded else 12,
        aligned_years=None if excluded else Decimal("1.00"),
        required_years=None if excluded else Decimal("2"),
        raw_value=None if excluded else Decimal(raw_value),
        evidence_refs=evidence_refs,
        provenance_refs=provenance_refs,
        exclusion_reason=(ExclusionReason.INSUFFICIENT_EVIDENCE if excluded else None),
        rationale=f"Experience result for {requirement_id}.",
    )


def test_multiple_evaluated_requirements_use_arithmetic_mean() -> None:
    result = aggregate_jd_aligned_experience(
        requirement_ids=("req-1", "req-2", "req-3"),
        evaluations=(
            _evaluation("req-1", raw_value="60"),
            _evaluation("req-2", raw_value="80"),
            _evaluation("req-3", raw_value="100"),
        ),
    )

    assert result.dimension is DimensionName.JD_ALIGNED_EXPERIENCE
    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("80.00")


def test_excluded_requirements_are_ignored_not_zeroed() -> None:
    result = aggregate_jd_aligned_experience(
        requirement_ids=("req-1", "req-2"),
        evaluations=(
            _evaluation("req-1", raw_value="80"),
            _evaluation("req-2", raw_value=None),
        ),
    )

    assert result.raw_value == Decimal("80.00")
    assert result.resolution is DimensionResolution.EVALUATED


def test_all_excluded_requirements_produce_excluded_dimension() -> None:
    result = aggregate_jd_aligned_experience(
        requirement_ids=("req-1",),
        evaluations=(_evaluation("req-1", raw_value=None),),
    )

    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.exclusion_reason is ExclusionReason.INSUFFICIENT_EVIDENCE


def test_zero_valued_evaluation_remains_evaluable() -> None:
    result = aggregate_jd_aligned_experience(
        requirement_ids=("req-1", "req-2"),
        evaluations=(
            _evaluation("req-1", raw_value="0"),
            _evaluation("req-2", raw_value="100"),
        ),
    )

    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("50.00")


def test_duplicate_requirement_evaluations_are_rejected() -> None:
    with pytest.raises(
        JDAlignedExperienceAggregationError,
        match="duplicate experience evaluation",
    ):
        aggregate_jd_aligned_experience(
            requirement_ids=("req-1",),
            evaluations=(
                _evaluation("req-1", raw_value="70"),
                _evaluation("req-1", raw_value="80"),
            ),
        )


def test_duplicate_known_requirement_ids_are_rejected() -> None:
    with pytest.raises(JDAlignedExperienceAggregationError, match="duplicate known"):
        aggregate_jd_aligned_experience(
            requirement_ids=("req-1", "req-1"),
            evaluations=(),
        )


def test_unknown_evaluation_requirement_is_rejected() -> None:
    with pytest.raises(JDAlignedExperienceAggregationError, match="unknown requirement"):
        aggregate_jd_aligned_experience(
            requirement_ids=("req-1",),
            evaluations=(_evaluation("unknown", raw_value="70"),),
        )


def test_non_decimal_evaluated_value_is_rejected() -> None:
    invalid = _evaluation("req-1", raw_value="70").model_copy(
        update={"raw_value": 70}
    )

    with pytest.raises(JDAlignedExperienceAggregationError, match="finite Decimal"):
        aggregate_jd_aligned_experience(
            requirement_ids=("req-1",),
            evaluations=(invalid,),
        )


def test_mean_uses_decimal_half_up_rounding() -> None:
    result = aggregate_jd_aligned_experience(
        requirement_ids=("req-1", "req-2"),
        evaluations=(
            _evaluation("req-1", raw_value="1.00"),
            _evaluation("req-2", raw_value="1.01"),
        ),
    )

    assert result.raw_value == Decimal("1.01")


def test_evidence_and_provenance_references_are_preserved() -> None:
    result = aggregate_jd_aligned_experience(
        requirement_ids=("req-1", "req-2"),
        evaluations=(
            _evaluation(
                "req-1",
                raw_value="70",
                evidence_refs=("evidence-1",),
                provenance_refs=("provenance-1",),
            ),
            _evaluation(
                "req-2",
                raw_value=None,
                evidence_refs=("evidence-2",),
                provenance_refs=("provenance-2",),
            ),
        ),
    )

    assert result.evidence_refs == ("evidence-1", "evidence-2")
    assert result.provenance_refs == ("provenance-1", "provenance-2")


def test_repeated_experience_aggregation_is_deterministic() -> None:
    requirement_ids = ("req-1", "req-2")
    evaluations = (
        _evaluation("req-1", raw_value="70.123"),
        _evaluation("req-2", raw_value="80.123"),
    )
    first = aggregate_jd_aligned_experience(
        requirement_ids=requirement_ids,
        evaluations=evaluations,
    )
    second = aggregate_jd_aligned_experience(
        requirement_ids=requirement_ids,
        evaluations=evaluations,
    )

    assert first.model_dump(exclude={"dimension_id", "created_at"}) == second.model_dump(
        exclude={"dimension_id", "created_at"}
    )
