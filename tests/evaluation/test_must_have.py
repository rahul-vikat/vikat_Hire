from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    DimensionResolution,
    ExclusionReason,
    MatchStatus,
)
from vikat_hire.contracts.evaluation import RequirementEvaluation
from vikat_hire.evaluation.must_have import (
    MustHaveEvaluationError,
    evaluate_must_have,
)


def requirement(
    *,
    requirement_id: str,
    status: MatchStatus,
    raw_score: str,
) -> RequirementEvaluation:
    return RequirementEvaluation(
        requirement_id=requirement_id,
        status=status,
        raw_score=Decimal(raw_score),
        evidence_refs=(),
        provenance_refs=(),
        rationale="Deterministic requirement evaluation.",
    )


def test_must_have_averages_all_evaluable_requirements() -> None:
    result = evaluate_must_have(
        evaluations=(
            requirement(
                requirement_id="req-python",
                status=MatchStatus.MATCHED,
                raw_score="100",
            ),
            requirement(
                requirement_id="req-fastapi",
                status=MatchStatus.PARTIAL,
                raw_score="70",
            ),
            requirement(
                requirement_id="req-docker",
                status=MatchStatus.NOT_MATCHED,
                raw_score="0",
            ),
        )
    )

    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("56.67")
    assert result.requirement_ids == (
        "req-docker",
        "req-fastapi",
        "req-python",
    )
    assert result.evaluated_requirement_ids == (
        "req-docker",
        "req-fastapi",
        "req-python",
    )
    assert result.excluded_requirement_ids == ()
    assert result.exclusion_reason is None


def test_unresolved_requirements_are_excluded_from_denominator() -> None:
    result = evaluate_must_have(
        evaluations=(
            requirement(
                requirement_id="req-python",
                status=MatchStatus.MATCHED,
                raw_score="100",
            ),
            requirement(
                requirement_id="req-fastapi",
                status=MatchStatus.UNRESOLVED,
                raw_score="0",
            ),
            requirement(
                requirement_id="req-docker",
                status=MatchStatus.NOT_MATCHED,
                raw_score="0",
            ),
        )
    )

    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("50.00")
    assert result.evaluated_requirement_ids == (
        "req-docker",
        "req-python",
    )
    assert result.excluded_requirement_ids == (
        "req-fastapi",
    )
    assert result.exclusion_reason is None


def test_not_matched_zero_remains_in_denominator() -> None:
    result = evaluate_must_have(
        evaluations=(
            requirement(
                requirement_id="req-python",
                status=MatchStatus.MATCHED,
                raw_score="100",
            ),
            requirement(
                requirement_id="req-docker",
                status=MatchStatus.NOT_MATCHED,
                raw_score="0",
            ),
        )
    )

    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("50.00")


def test_all_unresolved_requirements_exclude_group() -> None:
    result = evaluate_must_have(
        evaluations=(
            requirement(
                requirement_id="req-python",
                status=MatchStatus.UNRESOLVED,
                raw_score="0",
            ),
            requirement(
                requirement_id="req-fastapi",
                status=MatchStatus.UNRESOLVED,
                raw_score="0",
            ),
        )
    )

    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.requirement_ids == (
        "req-fastapi",
        "req-python",
    )
    assert result.evaluated_requirement_ids == ()
    assert result.excluded_requirement_ids == (
        "req-fastapi",
        "req-python",
    )
    assert (
        result.exclusion_reason
        is ExclusionReason.INSUFFICIENT_EVIDENCE
    )


def test_empty_requirement_group_is_excluded() -> None:
    result = evaluate_must_have(
        evaluations=(),
    )

    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.requirement_ids == ()
    assert result.evaluated_requirement_ids == ()
    assert result.excluded_requirement_ids == ()
    assert (
        result.exclusion_reason
        is ExclusionReason.INSUFFICIENT_EVIDENCE
    )


def test_decimal_average_is_rounded_half_up() -> None:
    result = evaluate_must_have(
        evaluations=(
            requirement(
                requirement_id="req-a",
                status=MatchStatus.PARTIAL,
                raw_score="10",
            ),
            requirement(
                requirement_id="req-b",
                status=MatchStatus.PARTIAL,
                raw_score="11",
            ),
            requirement(
                requirement_id="req-c",
                status=MatchStatus.PARTIAL,
                raw_score="12",
            ),
        )
    )

    assert result.raw_value == Decimal("11.00")


def test_duplicate_requirement_ids_fail_loudly() -> None:
    with pytest.raises(
        MustHaveEvaluationError,
        match="duplicate requirement evaluations",
    ):
        evaluate_must_have(
            evaluations=(
                requirement(
                    requirement_id="req-python",
                    status=MatchStatus.MATCHED,
                    raw_score="100",
                ),
                requirement(
                    requirement_id="req-python",
                    status=MatchStatus.PARTIAL,
                    raw_score="50",
                ),
            )
        )


def test_blank_requirement_id_fails_loudly() -> None:
    with pytest.raises(
        MustHaveEvaluationError,
        match="IDs must not be blank",
    ):
        evaluate_must_have(
            evaluations=(
                requirement(
                    requirement_id=" ",
                    status=MatchStatus.MATCHED,
                    raw_score="100",
                ),
            )
        )


def test_aggregation_is_deterministic_regardless_of_input_order() -> None:
    first = evaluate_must_have(
        evaluations=(
            requirement(
                requirement_id="req-b",
                status=MatchStatus.PARTIAL,
                raw_score="70",
            ),
            requirement(
                requirement_id="req-a",
                status=MatchStatus.MATCHED,
                raw_score="100",
            ),
        )
    )

    second = evaluate_must_have(
        evaluations=(
            requirement(
                requirement_id="req-a",
                status=MatchStatus.MATCHED,
                raw_score="100",
            ),
            requirement(
                requirement_id="req-b",
                status=MatchStatus.PARTIAL,
                raw_score="70",
            ),
        )
    )

    assert first == second
    assert first.raw_value == Decimal("85.00")