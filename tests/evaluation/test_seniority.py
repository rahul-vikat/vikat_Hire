from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    DimensionResolution,
    ExclusionReason,
    ScopeLevel,
)
from vikat_hire.evaluation.seniority import (
    evaluate_seniority_scope,
    scope_delta,
    scope_level_index,
    score_scope_delta,
)


def test_scope_level_order_is_l0_through_l5() -> None:
    assert [scope_level_index(level) for level in ScopeLevel] == [
        0,
        1,
        2,
        3,
        4,
        5,
    ]


@pytest.mark.parametrize(
    ("candidate", "required", "expected_delta"),
    [
        (ScopeLevel.L0, ScopeLevel.L0, 0),
        (ScopeLevel.L1, ScopeLevel.L0, 1),
        (ScopeLevel.L5, ScopeLevel.L0, 5),
        (ScopeLevel.L0, ScopeLevel.L1, -1),
        (ScopeLevel.L1, ScopeLevel.L3, -2),
        (ScopeLevel.L0, ScopeLevel.L5, -5),
    ],
)
def test_scope_delta(
    candidate: ScopeLevel,
    required: ScopeLevel,
    expected_delta: int,
) -> None:
    assert scope_delta(candidate, required) == expected_delta


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (-5, Decimal("20")),
        (-4, Decimal("20")),
        (-3, Decimal("20")),
        (-2, Decimal("45")),
        (-1, Decimal("75")),
        (0, Decimal("100")),
        (1, Decimal("90")),
        (2, Decimal("90")),
        (3, Decimal("90")),
        (4, Decimal("90")),
        (5, Decimal("90")),
    ],
)
def test_score_scope_delta_mapping(
    delta: int,
    expected: Decimal,
) -> None:
    assert score_scope_delta(delta) == expected


def test_scope_delta_mapping_is_decimal() -> None:
    result = score_scope_delta(-2)

    assert isinstance(result, Decimal)
    assert result == Decimal("45")


def test_evaluate_equal_scope_returns_100() -> None:
    result = evaluate_seniority_scope(
        candidate_level=ScopeLevel.L3,
        required_level=ScopeLevel.L3,
        evidence_refs=("candidate-scope-1",),
        provenance_refs=("candidate-provenance-1",),
    )

    assert result.resolution == DimensionResolution.EVALUATED
    assert result.candidate_level == ScopeLevel.L3
    assert result.required_level == ScopeLevel.L3
    assert result.delta == 0
    assert result.raw_value == Decimal("100")
    assert result.evidence_refs == ("candidate-scope-1",)
    assert result.provenance_refs == ("candidate-provenance-1",)


def test_evaluate_one_level_above_returns_90() -> None:
    result = evaluate_seniority_scope(
        candidate_level=ScopeLevel.L4,
        required_level=ScopeLevel.L3,
        evidence_refs=("scope-1",),
        provenance_refs=("provenance-1",),
    )

    assert result.delta == 1
    assert result.raw_value == Decimal("90")


def test_evaluate_multiple_levels_above_still_returns_90() -> None:
    result = evaluate_seniority_scope(
        candidate_level=ScopeLevel.L5,
        required_level=ScopeLevel.L1,
        evidence_refs=("scope-1",),
        provenance_refs=("provenance-1",),
    )

    assert result.delta == 4
    assert result.raw_value == Decimal("90")


def test_evaluate_one_level_below_returns_75() -> None:
    result = evaluate_seniority_scope(
        candidate_level=ScopeLevel.L2,
        required_level=ScopeLevel.L3,
        evidence_refs=("scope-1",),
        provenance_refs=("provenance-1",),
    )

    assert result.delta == -1
    assert result.raw_value == Decimal("75")


def test_evaluate_two_levels_below_returns_45() -> None:
    result = evaluate_seniority_scope(
        candidate_level=ScopeLevel.L2,
        required_level=ScopeLevel.L4,
        evidence_refs=("scope-1",),
        provenance_refs=("provenance-1",),
    )

    assert result.delta == -2
    assert result.raw_value == Decimal("45")


def test_evaluate_three_or_more_levels_below_returns_20() -> None:
    result = evaluate_seniority_scope(
        candidate_level=ScopeLevel.L0,
        required_level=ScopeLevel.L3,
        evidence_refs=("scope-1",),
        provenance_refs=("provenance-1",),
    )

    assert result.delta == -3
    assert result.raw_value == Decimal("20")


def test_evaluate_five_levels_below_returns_20() -> None:
    result = evaluate_seniority_scope(
        candidate_level=ScopeLevel.L0,
        required_level=ScopeLevel.L5,
        evidence_refs=("scope-1",),
        provenance_refs=("provenance-1",),
    )

    assert result.delta == -5
    assert result.raw_value == Decimal("20")


@pytest.mark.parametrize(
    ("candidate_level", "required_level"),
    [
        (None, ScopeLevel.L3),
        (ScopeLevel.L3, None),
        (None, None),
    ],
)
def test_missing_scope_is_excluded_not_zero(
    candidate_level: ScopeLevel | None,
    required_level: ScopeLevel | None,
) -> None:
    result = evaluate_seniority_scope(
        candidate_level=candidate_level,
        required_level=required_level,
        provenance_refs=("provenance-1",),
    )

    assert result.resolution == DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.delta is None
    assert result.exclusion_reason == ExclusionReason.INSUFFICIENT_EVIDENCE


def test_missing_candidate_scope_preserves_required_scope() -> None:
    result = evaluate_seniority_scope(
        candidate_level=None,
        required_level=ScopeLevel.L4,
        provenance_refs=("jd-provenance-1",),
    )

    assert result.required_level == ScopeLevel.L4
    assert result.candidate_level is None


def test_missing_required_scope_preserves_candidate_scope() -> None:
    result = evaluate_seniority_scope(
        candidate_level=ScopeLevel.L3,
        required_level=None,
        evidence_refs=("candidate-scope-1",),
        provenance_refs=("candidate-provenance-1",),
    )

    assert result.candidate_level == ScopeLevel.L3
    assert result.required_level is None


def test_missing_evidence_does_not_create_zero_score() -> None:
    result = evaluate_seniority_scope(
        candidate_level=None,
        required_level=ScopeLevel.L3,
        evidence_refs=(),
        provenance_refs=("jd-provenance-1",),
    )

    assert result.resolution == DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.raw_value != Decimal("0")


def test_scope_evaluation_does_not_apply_ten_percent_weight() -> None:
    result = evaluate_seniority_scope(
        candidate_level=ScopeLevel.L3,
        required_level=ScopeLevel.L3,
        provenance_refs=("provenance-1",),
    )

    # The evaluator emits the dimension's raw 0-100 value.
    # The scoring layer applies the configured 10% weight later.
    assert result.raw_value == Decimal("100")


def test_scope_evaluation_is_deterministic() -> None:
    kwargs = {
        "candidate_level": ScopeLevel.L2,
        "required_level": ScopeLevel.L4,
        "evidence_refs": ("scope-1",),
        "provenance_refs": ("provenance-1",),
    }

    first = evaluate_seniority_scope(**kwargs)
    second = evaluate_seniority_scope(**kwargs)

    assert first.model_dump(
        exclude={"created_at"}
    ) == second.model_dump(exclude={"created_at"})


def test_scope_evaluation_preserves_audit_references() -> None:
    result = evaluate_seniority_scope(
        candidate_level=ScopeLevel.L3,
        required_level=ScopeLevel.L2,
        evidence_refs=("evidence-1", "evidence-2"),
        provenance_refs=("provenance-1", "provenance-2"),
    )

    assert result.evidence_refs == ("evidence-1", "evidence-2")
    assert result.provenance_refs == ("provenance-1", "provenance-2")


def test_invalid_scope_level_index_fails_loudly() -> None:
    with pytest.raises(ValueError):
        scope_level_index("L6")  # type: ignore[arg-type]


def test_invalid_scope_delta_fails_loudly() -> None:
    with pytest.raises(ValueError):
        score_scope_delta(6_000)


def test_negative_invalid_scope_delta_fails_loudly() -> None:
    with pytest.raises(ValueError):
        score_scope_delta(-6_000)