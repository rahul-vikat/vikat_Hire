from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    DimensionResolution,
    ExclusionReason,
    MatchStatus,
)
from vikat_hire.contracts.evaluation import RequirementEvaluation
from vikat_hire.evaluation.aggregation import (
    RequirementAggregationError,
    aggregate_must_have_coverage,
    aggregate_nice_to_have_coverage,
)


def evaluation(
    requirement_id: str,
    status: MatchStatus,
    score: str,
) -> RequirementEvaluation:
    return RequirementEvaluation(
        requirement_id=requirement_id,
        status=status,
        raw_score=Decimal(score),
        evidence_refs=[],
        provenance_refs=[],
        rationale="test",
    )


def test_unresolved_requirement_is_excluded_from_denominator() -> None:
    evaluations = {
        "r1": evaluation("r1", MatchStatus.MATCHED, "100"),
        "r2": evaluation("r2", MatchStatus.UNRESOLVED, "0"),
    }

    result = aggregate_must_have_coverage(
        requirement_ids=("r1", "r2"),
        evaluations=evaluations,
    )

    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("100.00")
    assert result.evaluated_requirement_ids == ("r1",)
    assert result.excluded_requirement_ids == ("r2",)


def test_evaluated_zero_is_included_in_denominator() -> None:
    evaluations = {
        "r1": evaluation("r1", MatchStatus.MATCHED, "100"),
        "r2": evaluation("r2", MatchStatus.NOT_MATCHED, "0"),
    }

    result = aggregate_must_have_coverage(
        requirement_ids=("r1", "r2"),
        evaluations=evaluations,
    )

    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("50.00")
    assert result.evaluated_requirement_ids == ("r1", "r2")


def test_all_unresolved_requirements_are_excluded() -> None:
    evaluations = {
        "r1": evaluation("r1", MatchStatus.UNRESOLVED, "0"),
        "r2": evaluation("r2", MatchStatus.UNRESOLVED, "0"),
    }

    result = aggregate_nice_to_have_coverage(
        requirement_ids=("r1", "r2"),
        evaluations=evaluations,
    )

    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.exclusion_reason is ExclusionReason.INSUFFICIENT_EVIDENCE
    assert result.evaluated_requirement_ids == ()
    assert result.excluded_requirement_ids == ("r1", "r2")


def test_partial_and_not_matched_are_evaluated() -> None:
    evaluations = {
        "r1": evaluation("r1", MatchStatus.PARTIAL, "75"),
        "r2": evaluation("r2", MatchStatus.NOT_MATCHED, "25"),
    }

    result = aggregate_must_have_coverage(
        requirement_ids=("r1", "r2"),
        evaluations=evaluations,
    )

    assert result.raw_value == Decimal("50.00")


def test_duplicate_requirement_ids_fail() -> None:
    evaluations = {
        "r1": evaluation("r1", MatchStatus.MATCHED, "100"),
    }

    with pytest.raises(
        RequirementAggregationError,
        match="duplicate requirement IDs",
    ):
        aggregate_must_have_coverage(
            requirement_ids=("r1", "r1"),
            evaluations=evaluations,
        )


def test_missing_evaluation_fails() -> None:
    with pytest.raises(
        RequirementAggregationError,
        match="missing evaluations",
    ):
        aggregate_must_have_coverage(
            requirement_ids=("r1",),
            evaluations={},
        )


def test_empty_group_is_explicitly_excluded() -> None:
    result = aggregate_must_have_coverage(
        requirement_ids=(),
        evaluations={},
    )

    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.exclusion_reason is ExclusionReason.INSUFFICIENT_EVIDENCE