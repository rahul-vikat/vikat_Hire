from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from vikat_hire.contracts import (
    DimensionResolution,
    ExclusionReason,
    ExperienceEvaluation,
    ExperienceRecord,
    ExperienceRequirement,
    RequirementImportance,
)


def make_record(**overrides: object) -> ExperienceRecord:
    values: dict[str, object] = {
        "record_id": "exp-001",
        "employer": "Example Corp",
        "role": "Software Engineer",
        "start_date": date(2020, 1, 1),
        "end_date": date(2023, 12, 31),
        "provenance_refs": ("prov-001",),
        "evidence_refs": ("evidence-001",),
    }

    values.update(overrides)

    return ExperienceRecord(**values)


def make_requirement(**overrides: object) -> ExperienceRequirement:
    values: dict[str, object] = {
        "requirement_id": "req-exp-001",
        "text": "5 years of backend engineering experience",
        "importance": RequirementImportance.MUST_HAVE,
        "minimum_years": Decimal("5"),
        "canonical_skill_refs": ("skill-python",),
        "provenance_refs": ("prov-jd-001",),
    }

    values.update(overrides)

    return ExperienceRequirement(**values)


def test_valid_experience_record() -> None:
    record = make_record()

    assert record.record_id == "exp-001"
    assert record.start_date == date(2020, 1, 1)
    assert record.end_date == date(2023, 12, 31)


def test_end_date_before_start_date_is_rejected() -> None:
    with pytest.raises(
        ValidationError,
        match="end_date cannot precede start_date",
    ):
        make_record(
            start_date=date(2024, 1, 1),
            end_date=date(2023, 12, 31),
        )


def test_current_experience_cannot_have_end_date() -> None:
    with pytest.raises(
        ValidationError,
        match="current experience cannot have end_date",
    ):
        make_record(
            current=True,
            end_date=date(2024, 12, 31),
        )


def test_missing_dates_are_preserved() -> None:
    record = make_record(
        start_date=None,
        end_date=None,
    )

    assert record.start_date is None
    assert record.end_date is None


def test_experience_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        make_record(provenance_refs=())


def test_valid_experience_requirement() -> None:
    requirement = make_requirement()

    assert requirement.minimum_years == Decimal("5")
    assert requirement.importance is RequirementImportance.MUST_HAVE


def test_blank_experience_requirement_is_rejected() -> None:
    with pytest.raises(
        ValidationError,
        match="must not be blank",
    ):
        make_requirement(text="   ")


def test_zero_minimum_years_is_rejected() -> None:
    with pytest.raises(
        ValidationError,
        match="minimum_years must be positive",
    ):
        make_requirement(minimum_years=Decimal("0"))


def test_missing_minimum_years_is_allowed() -> None:
    requirement = make_requirement(
        minimum_years=None,
    )

    assert requirement.minimum_years is None


def test_evaluated_experience_requires_all_measurements() -> None:
    evaluation = ExperienceEvaluation(
        requirement_id="req-exp-001",
        resolution=DimensionResolution.EVALUATED,
        aligned_months=60,
        aligned_years=Decimal("5"),
        required_years=Decimal("5"),
        raw_value=Decimal("100"),
        contributing_record_ids=("exp-001",),
        evidence_refs=("evidence-001",),
        provenance_refs=("prov-001",),
        rationale="Five aligned years satisfy the requirement.",
    )

    assert evaluation.raw_value == Decimal("100")
    assert evaluation.aligned_months == 60


def test_evaluated_experience_zero_does_not_require_contributing_record() -> None:
    evaluation = ExperienceEvaluation(
        requirement_id="exp-001",
        resolution=DimensionResolution.EVALUATED,
        aligned_months=0,
        aligned_years=Decimal("0"),
        required_years=Decimal("5"),
        raw_value=Decimal("0"),
        contributing_record_ids=(),
        rationale="No aligned experience.",
    )

    assert evaluation.resolution is DimensionResolution.EVALUATED
    assert evaluation.raw_value == Decimal("0")
    assert evaluation.contributing_record_ids == ()
    assert evaluation.exclusion_reason is None


def test_excluded_experience_has_no_score() -> None:
    evaluation = ExperienceEvaluation(
        requirement_id="req-exp-001",
        resolution=DimensionResolution.EXCLUDED,
        aligned_months=0,
        exclusion_reason=ExclusionReason.NOT_APPLICABLE,
        rationale="The JD does not specify an experience requirement.",
    )

    assert evaluation.raw_value is None
    assert evaluation.aligned_years is None
    assert evaluation.required_years is None


def test_excluded_experience_cannot_have_raw_value() -> None:
    with pytest.raises(
        ValidationError,
        match="excluded experience cannot have raw_value",
    ):
        ExperienceEvaluation(
            requirement_id="req-exp-001",
            resolution=DimensionResolution.EXCLUDED,
            aligned_months=0,
            raw_value=Decimal("0"),
            exclusion_reason=ExclusionReason.NOT_APPLICABLE,
            rationale="Invalid excluded evaluation.",
        )


def test_evaluated_zero_is_distinct_from_excluded() -> None:
    evaluation = ExperienceEvaluation(
        requirement_id="req-exp-001",
        resolution=DimensionResolution.EVALUATED,
        aligned_months=0,
        aligned_years=Decimal("0"),
        required_years=Decimal("5"),
        raw_value=Decimal("0"),
        contributing_record_ids=("exp-001",),
        evidence_refs=("evidence-001",),
        provenance_refs=("prov-001",),
        rationale="Validated experience evidence does not meet the requirement.",
    )

    assert evaluation.resolution is DimensionResolution.EVALUATED
    assert evaluation.raw_value == Decimal("0")


def test_excluded_experience_cannot_have_contributing_records() -> None:
    with pytest.raises(
        ValidationError,
        match="excluded experience cannot have contributing records",
    ):
        ExperienceEvaluation(
            requirement_id="req-exp-001",
            resolution=DimensionResolution.EXCLUDED,
            aligned_months=0,
            contributing_record_ids=("exp-001",),
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
            rationale="Invalid excluded evaluation.",
        )


def test_experience_contracts_are_immutable() -> None:
    record = make_record()

    with pytest.raises(ValidationError):
        record.role = "Engineering Manager"  # type: ignore[misc]


def test_experience_evaluation_score_is_bounded() -> None:
    with pytest.raises(ValidationError):
        ExperienceEvaluation(
            requirement_id="req-exp-001",
            resolution=DimensionResolution.EVALUATED,
            aligned_months=60,
            aligned_years=Decimal("5"),
            required_years=Decimal("5"),
            raw_value=Decimal("101"),
            contributing_record_ids=("exp-001",),
            rationale="Invalid score.",
        )