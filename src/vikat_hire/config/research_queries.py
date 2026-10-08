"""Fixed query definitions for display-only company and college research."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from vikat_hire.contracts.research import ResearchDimension, ResearchEntityType


@dataclass(frozen=True)
class ResearchQueryDefinition:
    entity_type: ResearchEntityType
    dimension: ResearchDimension
    query_template: str

    def render(self, entity_name: str) -> str:
        if not isinstance(entity_name, str) or not entity_name.strip():
            raise ValueError("entity_name must not be blank")
        safe_name = entity_name.strip().replace('"', '\\"')
        return self.query_template.format(name=safe_name)


RESEARCH_QUERY_DEFINITIONS: tuple[ResearchQueryDefinition, ...] = (
    ResearchQueryDefinition(
        ResearchEntityType.COMPANY,
        ResearchDimension.FINANCIAL_VALUATION,
        '"{name}" funding valuation revenue investors',
    ),
    ResearchQueryDefinition(
        ResearchEntityType.COMPANY,
        ResearchDimension.MARKET_POSITION,
        '"{name}" customers products competitors market',
    ),
    ResearchQueryDefinition(
        ResearchEntityType.COMPANY,
        ResearchDimension.ENGINEERING_TECHNICAL,
        '"{name}" engineering technology AI patents research',
    ),
    ResearchQueryDefinition(
        ResearchEntityType.COMPANY,
        ResearchDimension.REPUTATION_COMPLIANCE,
        '"{name}" certifications compliance security reputation',
    ),
    ResearchQueryDefinition(
        ResearchEntityType.COLLEGE,
        ResearchDimension.OFFICIAL_RANKING,
        '"{name}" NIRF ranking QS THE ranking',
    ),
    ResearchQueryDefinition(
        ResearchEntityType.COLLEGE,
        ResearchDimension.ACCREDITATION,
        '"{name}" NAAC NBA UGC AICTE accreditation recognition',
    ),
    ResearchQueryDefinition(
        ResearchEntityType.COLLEGE,
        ResearchDimension.ACADEMIC_RESEARCH,
        '"{name}" research publications citations patents faculty',
    ),
    ResearchQueryDefinition(
        ResearchEntityType.COLLEGE,
        ResearchDimension.PLACEMENTS,
        '"{name}" placement report median salary recruiters placement',
    ),
    ResearchQueryDefinition(
        ResearchEntityType.COLLEGE,
        ResearchDimension.PERCEPTION_INFRASTRUCTURE,
        '"{name}" alumni campus infrastructure student life',
    ),
)

_QUERY_BY_KEY: Mapping[
    tuple[ResearchEntityType, ResearchDimension], ResearchQueryDefinition
] = MappingProxyType(
    {
        (definition.entity_type, definition.dimension): definition
        for definition in RESEARCH_QUERY_DEFINITIONS
    }
)


def get_research_query(
    *,
    entity_type: ResearchEntityType,
    dimension: ResearchDimension,
    entity_name: str,
) -> str:
    if not isinstance(entity_type, ResearchEntityType):
        raise ValueError("entity_type must be a ResearchEntityType")
    if not isinstance(dimension, ResearchDimension):
        raise ValueError("dimension must be a ResearchDimension")
    try:
        definition = _QUERY_BY_KEY[(entity_type, dimension)]
    except KeyError as exc:
        raise ValueError(
            f"no research query for {entity_type.value}/{dimension.value}"
        ) from exc
    return definition.render(entity_name)
