"""Caller-supplied exact requirement indicators; deliberately no default taxonomy."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def normalize_indicator(text: str) -> str:
    return " ".join(text.casefold().split())


class JDClassificationConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configuration_ref: str = Field(min_length=1)
    technical_indicators: tuple[str, ...] = Field(min_length=1)
    non_technical_indicators: tuple[str, ...] = Field(min_length=1)

    @field_validator("configuration_ref")
    @classmethod
    def nonblank_reference(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("configuration_ref must not be blank")
        return value

    @field_validator("technical_indicators", "non_technical_indicators")
    @classmethod
    def validate_indicators(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_indicator(value) for value in values)
        if any(not value for value in normalized):
            raise ValueError("indicators must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate normalized indicators")
        return normalized

    @model_validator(mode="after")
    def disjoint_indicators(self) -> "JDClassificationConfiguration":
        if set(self.technical_indicators) & set(self.non_technical_indicators):
            raise ValueError("technical and non-technical indicators must not overlap")
        return self
