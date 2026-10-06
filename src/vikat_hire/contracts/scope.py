from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator

from .common import ContractModel, ScopeLevel


class ScopeEvidenceCategory(StrEnum):
    OWNERSHIP = "ownership"
    TECHNICAL_DECISION_AUTHORITY = "technical_decision_authority"
    ARCHITECTURE = "architecture"
    PEOPLE_LEADERSHIP = "people_leadership"
    CROSS_TEAM_SCOPE = "cross_team_scope"
    PRODUCTION_OPERATIONAL_OWNERSHIP = "production_operational_ownership"
    ENGINEERING_STRATEGY = "engineering_strategy"


class ScopeEvidence(ContractModel):
    """
    Normalized, auditable evidence used by the deterministic scope classifier.

    `supervision_learning` is deliberately an attribute rather than an
    evidence category so the authoritative seven-category vocabulary remains
    unchanged.
    """

    evidence_id: str = Field(min_length=1)
    categories: tuple[ScopeEvidenceCategory, ...] = Field(min_length=1)
    supervision_learning: bool = False
    explicit_text: str = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("explicit_text")
    @classmethod
    def validate_explicit_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("explicit_text must not be blank")
        return value

    @field_validator("categories")
    @classmethod
    def validate_categories(
        cls,
        value: tuple[ScopeEvidenceCategory, ...],
    ) -> tuple[ScopeEvidenceCategory, ...]:
        if len(set(value)) != len(value):
            raise ValueError("categories must not contain duplicates")
        return value


class ScopeEvidenceProfile(ContractModel):
    """
    Deterministic summary of normalized evidence.

    This is not a score. It only records which explicit evidence signals
    survived normalization.
    """

    ownership: bool = False
    technical_decision_authority: bool = False
    architecture: bool = False
    people_leadership: bool = False
    cross_team_scope: bool = False
    production_operational_ownership: bool = False
    engineering_strategy: bool = False
    supervision_learning: bool = False

    evidence_refs: tuple[str, ...] = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)


class ScopeGate(ContractModel):
    """
    Immutable description of one deterministic level gate.

    `required_categories` must all be represented by independent normalized
    evidence. `supporting_categories` can strengthen the classification but
    cannot replace the required gate.
    """

    level: ScopeLevel
    required_categories: tuple[ScopeEvidenceCategory, ...] = ()
    supporting_categories: tuple[ScopeEvidenceCategory, ...] = ()
    requires_supervision_learning: bool = False
    rationale: str = Field(min_length=1)

    @field_validator("required_categories", "supporting_categories")
    @classmethod
    def validate_category_lists(
        cls,
        value: tuple[ScopeEvidenceCategory, ...],
    ) -> tuple[ScopeEvidenceCategory, ...]:
        if len(set(value)) != len(value):
            raise ValueError("scope gate category lists must not contain duplicates")
        return value

    def model_post_init(self, __context: object) -> None:
        overlap = set(self.required_categories).intersection(
            self.supporting_categories
        )
        if overlap:
            raise ValueError(
                "a scope category cannot be both required and supporting: "
                + ", ".join(sorted(category.value for category in overlap))
            )


class ScopeTaxonomyConfiguration(ContractModel):
    """
    Versioned immutable v2.2.0 scope taxonomy.

    This configuration contains classification gates only. It contains no
    scoring weights.
    """

    taxonomy_version: str = Field(min_length=1)
    gates: tuple[ScopeGate, ...] = Field(min_length=6)

    @field_validator("taxonomy_version")
    @classmethod
    def validate_taxonomy_version(cls, value: str) -> str:
        if value != "2.2.0":
            raise ValueError(
                "scope taxonomy configuration must use authoritative version 2.2.0"
            )
        return value

    @field_validator("gates")
    @classmethod
    def validate_gates(
        cls,
        value: tuple[ScopeGate, ...],
    ) -> tuple[ScopeGate, ...]:
        expected = {
            ScopeLevel.L0,
            ScopeLevel.L1,
            ScopeLevel.L2,
            ScopeLevel.L3,
            ScopeLevel.L4,
            ScopeLevel.L5,
        }
        actual = {gate.level for gate in value}

        if actual != expected:
            raise ValueError(
                "scope taxonomy must contain exactly one gate for every level L0-L5"
            )

        if len(value) != len(actual):
            raise ValueError("scope taxonomy cannot contain duplicate level gates")

        return value