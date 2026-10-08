from __future__ import annotations

import pytest

from vikat_hire.contracts.research import (
    RawResearchResult,
    ResearchDimension,
    ResearchEntityIdentity,
    ResearchEntityType,
)


@pytest.fixture
def company_entity() -> ResearchEntityIdentity:
    return ResearchEntityIdentity(
        entity_id="company-exp-1",
        entity_type=ResearchEntityType.COMPANY,
        name="VIKAT.AI",
        provider_id="company-123",
        universal_name="vikat-ai",
        linkedin_url="https://www.linkedin.com/company/vikat-ai/",
        source_ref="linkedin-profile-1",
        evidence_refs=("linkedin-block-1",),
        provenance_refs=("linkedin-provenance-1",),
    )


@pytest.fixture
def college_entity() -> ResearchEntityIdentity:
    return ResearchEntityIdentity(
        entity_id="college-edu-1",
        entity_type=ResearchEntityType.COLLEGE,
        name="IIT Patna",
        provider_id="school-42",
        linkedin_url="https://www.linkedin.com/company/iit-patna/",
        source_ref="linkedin-profile-1",
        evidence_refs=("linkedin-block-1",),
        provenance_refs=("linkedin-provenance-1",),
    )


@pytest.fixture
def research_result_factory():
    def make(
        entity_type: ResearchEntityType = ResearchEntityType.COMPANY,
        dimension: ResearchDimension | None = None,
        *,
        title: str = "VIKAT.AI funding and valuation",
        url: str = "https://news.example/vikat",
        content: str = "VIKAT.AI raised funding from investors.",
        result_id: str = "result-1",
        result_index: int = 0,
        entity_name: str | None = None,
    ) -> RawResearchResult:
        resolved_name = entity_name or (
            "VIKAT.AI" if entity_type is ResearchEntityType.COMPANY else "IIT Patna"
        )
        resolved_dimension = dimension or (
            ResearchDimension.FINANCIAL_VALUATION
            if entity_type is ResearchEntityType.COMPANY
            else ResearchDimension.OFFICIAL_RANKING
        )
        return RawResearchResult(
            result_id=result_id,
            entity_type=entity_type,
            entity_name=resolved_name,
            dimension=resolved_dimension,
            query=f'"{resolved_name}" query',
            result_index=result_index,
            title=title,
            url=url,
            content=content,
            provenance_refs=(f"searx-provenance-{result_id}",),
        )

    return make
