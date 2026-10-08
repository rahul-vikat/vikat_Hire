"""Contracts for unscored, raw organizational research collection."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from vikat_hire.contracts.common import ContractModel, Provenance


class ResearchEntityType(StrEnum):
    COMPANY = "company"
    COLLEGE = "college"


class ResearchDimension(StrEnum):
    FINANCIAL_VALUATION = "financial_valuation"
    MARKET_POSITION = "market_position"
    ENGINEERING_TECHNICAL = "engineering_technical"
    REPUTATION_COMPLIANCE = "reputation_compliance"
    OFFICIAL_RANKING = "official_ranking"
    ACCREDITATION = "accreditation"
    ACADEMIC_RESEARCH = "academic_research"
    PLACEMENTS = "placements"
    PERCEPTION_INFRASTRUCTURE = "perception_infrastructure"


class RawResearchResult(ContractModel):
    result_id: str = Field(min_length=1)
    entity_type: ResearchEntityType
    entity_name: str = Field(min_length=1)
    dimension: ResearchDimension
    query: str = Field(min_length=1)
    result_index: int = Field(ge=0)
    title: str
    url: str = Field(min_length=1)
    content: str
    provenance_refs: tuple[str, ...] = Field(min_length=1)


class ResearchSearchBatch(ContractModel):
    entity_type: ResearchEntityType
    entity_name: str = Field(min_length=1)
    dimension: ResearchDimension
    query: str = Field(min_length=1)
    results: tuple[RawResearchResult, ...] = ()
    provenances: tuple[Provenance, ...] = ()

    @model_validator(mode="after")
    def validate_results_and_provenance(self) -> ResearchSearchBatch:
        known_provenance_ids = {
            provenance.provenance_id for provenance in self.provenances
        }
        result_ids: set[str] = set()
        for result in self.results:
            if result.result_id in result_ids:
                raise ValueError(
                    f"duplicate raw research result ID: {result.result_id}"
                )
            result_ids.add(result.result_id)
            if (
                result.entity_type is not self.entity_type
                or result.entity_name != self.entity_name
                or result.dimension is not self.dimension
                or result.query != self.query
            ):
                raise ValueError(
                    "raw research result context does not match its batch"
                )
            missing = set(result.provenance_refs) - known_provenance_ids
            if missing:
                raise ValueError(
                    "raw research result contains unknown provenance refs: "
                    f"{sorted(missing)}"
                )
        return self
