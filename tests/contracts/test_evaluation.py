from decimal import Decimal

from vikat_hire.contracts import (
    ApplicabilityStatus,
    DimensionEvaluation,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
)


def test_excluded_dimension_is_not_evaluated_zero() -> None:
    excluded = DimensionEvaluation(
        dimension=DimensionName.GITHUB_EVIDENCE,
        applicability=ApplicabilityStatus.NOT_APPLICABLE,
        resolution=DimensionResolution.EXCLUDED,
        raw_value=None,
        exclusion_reason=ExclusionReason.NOT_APPLICABLE,
        rationale="GitHub is not applicable to this screening.",
    )

    assert excluded.resolution is DimensionResolution.EXCLUDED
    assert excluded.raw_value is None


def test_evaluated_zero_is_distinct_from_exclusion() -> None:
    zero = DimensionEvaluation(
        dimension=DimensionName.MUST_HAVE_COVERAGE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("0"),
        rationale="No mandatory requirement was satisfied.",
    )

    assert zero.resolution is DimensionResolution.EVALUATED
    assert zero.raw_value == Decimal("0")