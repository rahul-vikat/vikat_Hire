from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import Field, field_validator , model_validator

from .common import (
    ApplicabilityStatus,
    ContractModel,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    MatchStatus,
    RequirementImportance,
    new_id,
    validate_score,
    utc_now,
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
    def raw_value_must_be_valid(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        return validate_score(value)


class EvaluationResult(ContractModel):
    screening_id: str

    dimensions: tuple[DimensionEvaluation, ...]

    contradiction_refs: tuple[str, ...] = ()

    deterministic: bool = True

    created_at: datetime = Field(default_factory=utc_now)

class RequirementGroupEvaluation(ContractModel):
    """Aggregated evaluation for one requirement-importance group."""

    importance: RequirementImportance
    resolution: DimensionResolution
    raw_value: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    requirement_ids: tuple[str, ...] = ()
    evaluated_requirement_ids: tuple[str, ...] = ()
    excluded_requirement_ids: tuple[str, ...] = ()
    exclusion_reason: ExclusionReason | None = None


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
                    "evaluated requirement group cannot have exclusion_reason"
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