from datetime import date
from decimal import Decimal

import pytest

from vikat_hire.contracts import (
    DimensionResolution,
    ExclusionReason,
    ExperienceRecord,
    ExperienceRequirement,
    RequirementImportance,
)
from vikat_hire.evaluation.experience import (
    ExperienceEvaluationError,
    evaluate_jd_aligned_experience,
)


def make_record(
    record_id: str,
    start_date: date | None,
    end_date: date | None,
    *,
    current: bool = False,
    evidence_refs: tuple[str, ...] = (),
    provenance_refs: tuple[str, ...] = ("prov-001",),
) -> ExperienceRecord:
    return ExperienceRecord(
        record_id=record_id,
        employer=f"Company {record_id}",
        role="Software Engineer",
        start_date=start_date,
        end_date=end_date,
        current=current,
        provenance_refs=provenance_refs,
        evidence_refs=evidence_refs,
    )


def make_requirement(
    minimum_years: str | None = "5",
) -> ExperienceRequirement:
    return ExperienceRequirement(
        requirement_id="req-exp-001",
        text="5 years of backend engineering experience",
        importance=RequirementImportance.MUST_HAVE,
        minimum_years=(
            Decimal(minimum_years)
            if minimum_years is not None
            else None
        ),
        canonical_skill_refs=("skill-python",),
        provenance_refs=("jd-prov-001",),
    )


def test_five_unique_years_produces_100() -> None:
    records = (
        make_record(
            "exp-001",
            date(2020, 1, 1),
            date(2024, 12, 31),
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2025, 1, 1),
    )

    assert result.resolution is DimensionResolution.EVALUATED
    assert result.aligned_months == 60
    assert result.aligned_years == Decimal("5.00")
    assert result.required_years == Decimal("5")
    assert result.raw_value == Decimal("100.00")


def test_three_years_against_five_year_requirement_produces_60() -> None:
    records = (
        make_record(
            "exp-001",
            date(2022, 1, 1),
            date(2024, 12, 31),
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2025, 1, 1),
    )

    assert result.aligned_months == 36
    assert result.aligned_years == Decimal("3.00")
    assert result.raw_value == Decimal("60.00")


def test_overlapping_employment_does_not_double_count_months() -> None:
    records = (
        make_record(
            "exp-a",
            date(2020, 1, 1),
            date(2023, 12, 31),
        ),
        make_record(
            "exp-b",
            date(2022, 1, 1),
            date(2024, 12, 31),
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset(
            {"exp-a", "exp-b"}
        ),
        as_of_date=date(2025, 1, 1),
    )

    # Jan 2020 through Dec 2024 = 60 unique months.
    assert result.aligned_months == 60
    assert result.aligned_years == Decimal("5.00")
    assert result.raw_value == Decimal("100.00")

    assert result.contributing_record_ids == (
        "exp-a",
        "exp-b",
    )


def test_partial_overlap_counts_each_month_once() -> None:
    records = (
        make_record(
            "exp-a",
            date(2020, 1, 1),
            date(2022, 12, 31),
        ),
        make_record(
            "exp-b",
            date(2022, 7, 1),
            date(2023, 6, 30),
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("4"),
        matched_record_ids=frozenset(
            {"exp-a", "exp-b"}
        ),
        as_of_date=date(2024, 1, 1),
    )

    # Jan 2020 through Jun 2023 = 42 unique months.
    assert result.aligned_months == 42
    assert result.aligned_years == Decimal("3.50")
    assert result.raw_value == Decimal("87.50")


def test_score_is_capped_at_100() -> None:
    records = (
        make_record(
            "exp-001",
            date(2015, 1, 1),
            date(2024, 12, 31),
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2025, 1, 1),
    )

    assert result.aligned_months == 120
    assert result.aligned_years == Decimal("10.00")
    assert result.raw_value == Decimal("100.00")


def test_current_experience_uses_as_of_date() -> None:
    records = (
        make_record(
            "exp-001",
            date(2022, 1, 1),
            None,
            current=True,
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2024, 12, 15),
    )

    # Jan 2022 through Dec 2024 = 36 calendar months.
    assert result.aligned_months == 36
    assert result.aligned_years == Decimal("3.00")
    assert result.raw_value == Decimal("60.00")


def test_current_experience_is_not_allowed_to_use_future_date() -> None:
    records = (
        make_record(
            "exp-001",
            date(2022, 1, 1),
            None,
            current=True,
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2024, 12, 15),
    )

    assert result.aligned_months == 36


def test_missing_dates_do_not_create_experience() -> None:
    records = (
        make_record(
            "exp-001",
            None,
            None,
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2025, 1, 1),
    )

    assert result.resolution is DimensionResolution.EVALUATED
    assert result.aligned_months == 0
    assert result.aligned_years == Decimal("0.00")
    assert result.raw_value == Decimal("0.00")
    assert result.contributing_record_ids == ()


def test_unmatched_record_does_not_contribute() -> None:
    records = (
        make_record(
            "exp-001",
            date(2020, 1, 1),
            date(2024, 12, 31),
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset(),
        as_of_date=date(2025, 1, 1),
    )

    assert result.aligned_months == 0
    assert result.raw_value == Decimal("0.00")
    assert result.contributing_record_ids == ()
    assert result.excluded_record_ids == ("exp-001",)


def test_no_minimum_experience_requirement_is_excluded() -> None:
    records = (
        make_record(
            "exp-001",
            date(2020, 1, 1),
            date(2024, 12, 31),
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement(None),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2025, 1, 1),
    )

    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.aligned_years is None
    assert result.required_years is None
    assert result.exclusion_reason is ExclusionReason.NOT_APPLICABLE


def test_evaluated_zero_is_not_excluded() -> None:
    records = (
        make_record(
            "exp-001",
            None,
            None,
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2025, 1, 1),
    )

    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("0.00")
    assert result.exclusion_reason is None


def test_unknown_matched_record_is_rejected() -> None:
    records = (
        make_record(
            "exp-001",
            date(2020, 1, 1),
            date(2024, 12, 31),
        ),
    )

    with pytest.raises(
        ExperienceEvaluationError,
        match="unknown records",
    ):
        evaluate_jd_aligned_experience(
            records=records,
            requirement=make_requirement("5"),
            matched_record_ids=frozenset({"exp-999"}),
            as_of_date=date(2025, 1, 1),
        )


def test_duplicate_record_ids_are_rejected() -> None:
    records = (
        make_record(
            "exp-001",
            date(2020, 1, 1),
            date(2022, 12, 31),
        ),
        make_record(
            "exp-001",
            date(2023, 1, 1),
            date(2024, 12, 31),
        ),
    )

    with pytest.raises(
        ExperienceEvaluationError,
        match="duplicate experience record_id",
    ):
        evaluate_jd_aligned_experience(
            records=records,
            requirement=make_requirement("5"),
            matched_record_ids=frozenset({"exp-001"}),
            as_of_date=date(2025, 1, 1),
        )


def test_evidence_is_merged_from_contributing_records() -> None:
    records = (
        make_record(
            "exp-001",
            date(2020, 1, 1),
            date(2024, 12, 31),
            evidence_refs=(
                "evidence-001",
                "evidence-002",
            ),
            provenance_refs=(
                "prov-001",
                "prov-002",
            ),
        ),
    )

    result = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2025, 1, 1),
    )

    assert result.evidence_refs == (
        "evidence-001",
        "evidence-002",
    )

    assert result.provenance_refs == (
        "jd-prov-001",
        "prov-001",
        "prov-002",
    )


def test_result_is_deterministic_for_same_inputs() -> None:
    records = (
        make_record(
            "exp-001",
            date(2020, 1, 1),
            date(2024, 12, 31),
        ),
    )

    first = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2025, 1, 1),
    )

    second = evaluate_jd_aligned_experience(
        records=records,
        requirement=make_requirement("5"),
        matched_record_ids=frozenset({"exp-001"}),
        as_of_date=date(2025, 1, 1),
    )

    assert first == second