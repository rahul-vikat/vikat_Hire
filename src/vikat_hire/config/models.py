from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

from vikat_hire.contracts.common import DimensionName


class ScoringRelease(BaseModel):
    """Immutable identity and metadata for a scoring release."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )

    release: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    description: str = Field(min_length=1)

    @field_validator("release", "schema_version", "description")
    @classmethod
    def reject_blank_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class ImmutableScoringConfiguration(BaseModel):
    """
    Immutable, versioned scoring configuration.

    This class contains configuration only.
    It does not perform score calculation.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )

    release: ScoringRelease
    weights: Mapping[DimensionName, Decimal]

    @field_validator("weights")
    @classmethod
    def validate_weights(
        cls,
        value: Mapping[DimensionName, Decimal],
    ) -> Mapping[DimensionName, Decimal]:
        expected_dimensions = frozenset(DimensionName)
        actual_dimensions = frozenset(value.keys())

        missing = expected_dimensions - actual_dimensions
        if missing:
            raise ValueError(
                "scoring configuration is missing dimensions: "
                + ", ".join(
                    sorted(dimension.value for dimension in missing)
                )
            )

        unexpected = actual_dimensions - expected_dimensions
        if unexpected:
            raise ValueError(
                "scoring configuration contains unexpected dimensions: "
                + ", ".join(sorted(str(dimension) for dimension in unexpected))
            )

        for dimension, weight in value.items():
            if not isinstance(weight, Decimal):
                raise TypeError(
                    f"weight for {dimension.value} must be Decimal"
                )

            if weight < Decimal("0"):
                raise ValueError(
                    f"weight for {dimension.value} must not be negative"
                )

        total = sum(value.values(), Decimal("0"))

        if total != Decimal("100"):
            raise ValueError(
                f"scoring weights must sum to exactly 100; got {total}"
            )

        # MappingProxyType gives us deep protection for the mapping itself,
        # while the Pydantic serializer below converts it back to a normal
        # mapping for serialization.
        return MappingProxyType(dict(value))

    @field_serializer("weights")
    def serialize_weights(
        self,
        value: Mapping[DimensionName, Decimal],
    ) -> dict[DimensionName, Decimal]:
        return dict(value)

    def weight_for(self, dimension: DimensionName) -> Decimal:
        """Return the configured weight for one dimension."""

        try:
            return self.weights[dimension]
        except KeyError as exc:
            raise KeyError(
                f"no scoring weight configured for {dimension.value}"
            ) from exc

    @property
    def total_weight(self) -> Decimal:
        """Return the configured total weight."""

        return sum(self.weights.values(), Decimal("0"))