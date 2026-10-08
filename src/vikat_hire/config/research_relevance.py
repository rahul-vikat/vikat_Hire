"""Explicit lexical relevance terms for display-only entity research."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from vikat_hire.contracts.research import ResearchDimension, ResearchEntityType

COMPANY_RELEVANCE_TERMS: Mapping[ResearchDimension, tuple[str, ...]] = MappingProxyType(
    {
        ResearchDimension.FINANCIAL_VALUATION: (
            "financial",
            "funding",
            "valuation",
            "revenue",
            "investors",
            "investment",
        ),
        ResearchDimension.MARKET_POSITION: (
            "market",
            "position",
            "customers",
            "products",
            "competitors",
        ),
        ResearchDimension.ENGINEERING_TECHNICAL: (
            "engineering",
            "technical",
            "technology",
            "AI",
            "patents",
            "research",
        ),
        ResearchDimension.REPUTATION_COMPLIANCE: (
            "reputation",
            "certifications",
            "compliance",
            "security",
        ),
    }
)

COLLEGE_RELEVANCE_TERMS: Mapping[ResearchDimension, tuple[str, ...]] = MappingProxyType(
    {
        ResearchDimension.OFFICIAL_RANKING: (
            "official",
            "ranking",
            "NIRF",
            "QS",
            "THE ranking",
        ),
        ResearchDimension.ACCREDITATION: (
            "accreditation",
            "NAAC",
            "NBA",
            "UGC",
            "AICTE",
            "recognition",
        ),
        ResearchDimension.ACADEMIC_RESEARCH: (
            "academic",
            "research",
            "publications",
            "citations",
            "patents",
            "faculty",
        ),
        ResearchDimension.PLACEMENTS: (
            "placements",
            "placement",
            "placement report",
            "median salary",
            "recruiters",
        ),
        ResearchDimension.PERCEPTION_INFRASTRUCTURE: (
            "perception",
            "infrastructure",
            "alumni",
            "campus",
            "student life",
        ),
    }
)

RESEARCH_RELEVANCE_TERMS: Mapping[
    ResearchEntityType,
    Mapping[ResearchDimension, tuple[str, ...]],
] = MappingProxyType(
    {
        ResearchEntityType.COMPANY: COMPANY_RELEVANCE_TERMS,
        ResearchEntityType.COLLEGE: COLLEGE_RELEVANCE_TERMS,
    }
)
