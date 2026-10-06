from __future__ import annotations

from decimal import Decimal
from datetime import datetime

from pydantic import Field, field_validator, model_validator

from .common import ContractModel, DimensionName, DimensionResolution, new_id, utc_now
from .evaluation import DimensionEvaluation


class ScoringConfiguration(ContractModel):
    config_id: str = Field(default_factory=new_id)
    release: str = Field(min_length=1)
    weights: dict[DimensionName, Decimal]

    @field_validator("weights")
    @classmethod
    def validate_weights(
        cls,
        value: dict[DimensionName, Decimal],
    ) -> dict[DimensionName, Decimal]:
        expected = set(DimensionName)

        if set(value) != expected:
            missing = expected - set(value)
            unexpected = set(value) - expected

            parts: list[str] = []

            if missing:
                parts.append(
                    "missing="
                    + ",".join(sorted(item.value for item in missing))
                )

            if unexpected:
                parts.append(
                    "unexpected="
                    + ",".join(sorted(str(item) for item in unexpected))
                )

            raise ValueError(
                "weights must contain exactly all scoring dimensions: "
                + "; ".join(parts)
            )

        for dimension, weight in value.items():
            if not isinstance(weight, Decimal):
                raise TypeError(
                    f"{dimension.value} weight must be Decimal"
                )

            if weight < Decimal("0"):
                raise ValueError(
                    f"{dimension.value} weight cannot be negative"
                )

        total = sum(value.values(), Decimal("0"))

        if total != Decimal("100"):
            raise ValueError(
                f"weights must sum to exactly 100; got {total}"
            )

        return value


class DimensionScore(ContractModel):
    dimension: DimensionName
    resolution: DimensionResolution
    weight: Decimal
    raw_value: Decimal | None = None
    normalized_value: Decimal | None = None
    weighted_contribution: Decimal = Decimal("0")
    evidence_refs: tuple[str, ...] = ()

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, value: Decimal) -> Decimal:
        if value < Decimal("0") or value > Decimal("100"):
            raise ValueError("weight must be between 0 and 100")
        return value

    @field_validator("raw_value")
    @classmethod
    def validate_raw_value(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and (
            value < Decimal("0") or value > Decimal("100")
        ):
            raise ValueError("raw_value must be between 0 and 100")
        return value

    @field_validator("normalized_value")
    @classmethod
    def validate_normalized_value(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and (
            value < Decimal("0") or value > Decimal("1")
        ):
            raise ValueError("normalized_value must be between 0 and 1")
        return value

    @field_validator("weighted_contribution")
    @classmethod
    def validate_contribution(cls, value: Decimal) -> Decimal:
        if value < Decimal("0"):
            raise ValueError("weighted_contribution cannot be negative")
        return value

    @model_validator(mode="after")
    def validate_resolution_state(self) -> "DimensionScore":
        if self.resolution is DimensionResolution.EVALUATED:
            if self.raw_value is None:
                raise ValueError(
                    "evaluated dimension must have raw_value"
                )

            if self.normalized_value is None:
                raise ValueError(
                    "evaluated dimension must have normalized_value"
                )

        elif self.resolution is DimensionResolution.EXCLUDED:
            if self.raw_value is not None:
                raise ValueError(
                    "excluded dimension must not have raw_value"
                )

            if self.normalized_value is not None:
                raise ValueError(
                    "excluded dimension must not have normalized_value"
                )

            if self.weighted_contribution != Decimal("0"):
                raise ValueError(
                    "excluded dimension must have zero contribution"
                )

        return self


class ScoreAudit(ContractModel):
    audit_id: str = Field(default_factory=new_id)
    dimension: DimensionName
    input_evaluation_ref: str
    evidence_refs: tuple[str, ...] = ()
    configuration_ref: str
    weight: Decimal
    normalized_value: Decimal
    weighted_contribution: Decimal
    created_at: datetime = Field(default_factory=utc_now)


class ScoreResult(ContractModel):
    screening_id: str
    dimensions: tuple[DimensionScore, ...]
    applicable_weight_total: Decimal
    score: Decimal | None
    audit: tuple[ScoreAudit, ...]
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("applicable_weight_total")
    @classmethod
    def validate_applicable_weight(
        cls,
        value: Decimal,
    ) -> Decimal:
        if value < Decimal("0") or value > Decimal("100"):
            raise ValueError(
                "applicable_weight_total must be between 0 and 100"
            )
        return value

    @field_validator("score")
    @classmethod
    def validate_score(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and (
            value < Decimal("0") or value > Decimal("100")
        ):
            raise ValueError("score must be between 0 and 100")
        return value