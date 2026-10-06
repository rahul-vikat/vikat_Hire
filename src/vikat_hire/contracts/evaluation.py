from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from .common import (
    ApplicabilityStatus,
    ContractModel,
    DatePrecision,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    MatchStatus,
    ScopeLevel,
    RequirementImportance,
    new_id,
    utc_now,
    validate_score,
)


class RequirementEvaluation(ContractModel):
    requirement_id: str

    status: MatchStatus

    raw_score: Decimal

    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    rationale: str

    @field_validator("raw_score")
    @classmethod
    def score_must_be_valid(cls, value: Decimal) -> Decimal:
        return validate_score(value)


class DimensionEvaluation(ContractModel):
    dimension_id: str = Field(default_factory=new_id)

    dimension: DimensionName

    applicability: ApplicabilityStatus
    resolution: DimensionResolution

    raw_value: Decimal | None = None

    exclusion_reason: ExclusionReason | None = None

    evidence_refs: tuple[str, ...] = ()
    requirement_refs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    rationale: str

    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("raw_value")
    @classmethod
    def raw_value_must_be_valid(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is None:
            return value

        return validate_score(value)


class EvaluationResult(ContractModel):
    screening_id: str

    dimensions: tuple[DimensionEvaluation, ...]

    contradiction_refs: tuple[str, ...] = ()

    deterministic: bool = True

    created_at: datetime = Field(default_factory=utc_now)

class SeniorityScopeEvaluation(ContractModel):
    """Deterministic evaluation of candidate scope against required scope.

    The evaluator that creates this contract is responsible for applying
    the authoritative L0-L5 delta mapping. This contract only represents
    the validated result and its audit references.
    """

    dimension: DimensionName = DimensionName.SENIORITY_SCOPE_ALIGNMENT

    candidate_level: ScopeLevel | None = None
    required_level: ScopeLevel | None = None

    resolution: DimensionResolution

    delta: int | None = None

    raw_value: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("100"),
    )

    evidence_refs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    exclusion_reason: ExclusionReason | None = None
    rationale: str

    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("rationale")
    @classmethod
    def rationale_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rationale must not be blank")
        return value

    @field_validator("delta")
    @classmethod
    def delta_must_be_in_valid_range(cls, value: int | None) -> int | None:
        if value is None:
            return value

        if value < -5 or value > 5:
            raise ValueError("delta must be between -5 and 5")

        return value

    @model_validator(mode="after")
    def validate_resolution(self) -> "SeniorityScopeEvaluation":
        if self.resolution == DimensionResolution.EVALUATED:
            if self.candidate_level is None:
                raise ValueError(
                    "evaluated seniority scope requires candidate_level"
                )

            if self.required_level is None:
                raise ValueError(
                    "evaluated seniority scope requires required_level"
                )

            if self.delta is None:
                raise ValueError(
                    "evaluated seniority scope requires delta"
                )

            if self.raw_value is None:
                raise ValueError(
                    "evaluated seniority scope requires raw_value"
                )

            if self.exclusion_reason is not None:
                raise ValueError(
                    "evaluated seniority scope cannot have exclusion_reason"
                )

        elif self.resolution == DimensionResolution.EXCLUDED:
            if self.delta is not None:
                raise ValueError(
                    "excluded seniority scope cannot have delta"
                )

            if self.raw_value is not None:
                raise ValueError(
                    "excluded seniority scope cannot have raw_value"
                )

            if self.exclusion_reason is None:
                raise ValueError(
                    "excluded seniority scope requires exclusion_reason"
                )

        return self

class RequirementGroupEvaluation(ContractModel):
    """Aggregated evaluation for one requirement-importance group."""

    importance: RequirementImportance

    resolution: DimensionResolution

    raw_value: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("100"),
    )

    requirement_ids: tuple[str, ...] = ()

    evaluated_requirement_ids: tuple[str, ...] = ()

    excluded_requirement_ids: tuple[str, ...] = ()

    exclusion_reason: ExclusionReason | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> "RequirementGroupEvaluation":
        if self.resolution is DimensionResolution.EVALUATED:
            if self.raw_value is None:
                raise ValueError(
                    "evaluated requirement group must have raw_value"
                )

            if self.exclusion_reason is not None:
                raise ValueError(
                    "evaluated requirement group cannot have "
                    "exclusion_reason"
                )

        if self.resolution is DimensionResolution.EXCLUDED:
            if self.raw_value is not None:
                raise ValueError(
                    "excluded requirement group cannot have raw_value"
                )

            if self.exclusion_reason is None:
                raise ValueError(
                    "excluded requirement group must have exclusion_reason"
                )

        return self


class ExperienceRecord(ContractModel):
    """
    Normalized candidate experience used by deterministic evaluation.

    This contract represents evidence only. It does not calculate
    JD-aligned experience or apply scoring weights.
    """

    record_id: str

    employer: str | None = None

    role: str | None = None

    start_date: date | None = None

    end_date: date | None = None

    date_precision: DatePrecision = DatePrecision.UNKNOWN

    current: bool = False

    skill_refs: tuple[str, ...] = ()

    responsibility_refs: tuple[str, ...] = ()

    provenance_refs: tuple[str, ...] = Field(min_length=1)

    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_dates(self) -> "ExperienceRecord":
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError(
                "experience end_date cannot precede start_date"
            )

        if self.current and self.end_date is not None:
            raise ValueError(
                "current experience cannot have end_date"
            )

        return self


class ExperienceRequirement(ContractModel):
    """
    JD-side experience requirement.

    minimum_years is the JD-required aligned experience threshold.
    """

    requirement_id: str

    text: str

    importance: RequirementImportance

    minimum_years: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
    )

    canonical_skill_refs: tuple[str, ...] = ()

    responsibility_refs: tuple[str, ...] = ()

    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "experience requirement text must not be blank"
            )

        return value

    @model_validator(mode="after")
    def validate_minimum_years(self) -> "ExperienceRequirement":
        if self.minimum_years == Decimal("0"):
            raise ValueError(
                "minimum_years must be positive when specified"
            )

        return self


class ExperienceEvaluation(ContractModel):
    """
    Deterministic and auditable JD-aligned experience result.

    The evaluator produces the raw 0-100 dimension value.
    The 2.2.0 scoring layer applies the configured 20% dimension weight.
    """

    requirement_id: str

    resolution: DimensionResolution

    aligned_months: int = Field(ge=0)

    aligned_years: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
    )

    required_years: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
    )

    raw_value: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("100"),
    )

    contributing_record_ids: tuple[str, ...] = ()

    excluded_record_ids: tuple[str, ...] = ()

    evidence_refs: tuple[str, ...] = ()

    provenance_refs: tuple[str, ...] = ()

    exclusion_reason: ExclusionReason | None = None

    rationale: str

    @model_validator(mode="after")
    def validate_resolution(self) -> "ExperienceEvaluation":
        if self.resolution is DimensionResolution.EVALUATED:
            if self.aligned_years is None:
                raise ValueError(
                    "evaluated experience requires aligned_years"
                )

            if self.required_years is None:
                raise ValueError(
                    "evaluated experience requires required_years"
                )

            if self.raw_value is None:
                raise ValueError(
                    "evaluated experience requires raw_value"
                )

            if self.exclusion_reason is not None:
                raise ValueError(
                    "evaluated experience cannot have exclusion_reason"
                )

            # if not self.contributing_record_ids:
            #     raise ValueError(
            #         "evaluated experience requires contributing records"
            #     )

        if self.resolution is DimensionResolution.EXCLUDED:
            if self.raw_value is not None:
                raise ValueError(
                    "excluded experience cannot have raw_value"
                )

            if self.exclusion_reason is None:
                raise ValueError(
                    "excluded experience requires exclusion_reason"
                )

            if self.aligned_years is not None:
                raise ValueError(
                    "excluded experience cannot have aligned_years"
                )

            if self.required_years is not None:
                raise ValueError(
                    "excluded experience cannot have required_years"
                )

            if self.contributing_record_ids:
                raise ValueError(
                    "excluded experience cannot have contributing records"
                )

        return self