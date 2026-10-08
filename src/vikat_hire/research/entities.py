from __future__ import annotations

from collections.abc import Iterable

from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.normalization import (
    NormalizedEducationRecord,
    NormalizedExperienceRecord,
)
from vikat_hire.contracts.research import (
    ResearchEntityIdentity,
    ResearchEntityType,
)


def build_research_entities(
    *,
    experience_records: Iterable[NormalizedExperienceRecord],
    education_records: Iterable[NormalizedEducationRecord],
) -> tuple[ResearchEntityIdentity, ...]:
    """Build research targets only from identity fields in normalized LinkedIn data."""
    entities: list[ResearchEntityIdentity] = []
    seen_ids: set[str] = set()

    for record in experience_records:
        if not isinstance(record, NormalizedExperienceRecord):
            raise TypeError("experience_records must contain normalized records")
        if record.source_type is not SourceType.LINKEDIN:
            continue
        if record.employer is None:
            continue
        entity = ResearchEntityIdentity(
            entity_id=record.record_id,
            entity_type=ResearchEntityType.COMPANY,
            name=record.employer,
            provider_id=record.company_id,
            universal_name=record.company_universal_name,
            linkedin_url=record.company_linkedin_url,
            source_ref=record.source_ref,
            evidence_refs=record.evidence_refs,
            provenance_refs=record.provenance_refs,
        )
        _append_unique(entities, seen_ids, entity)

    for record in education_records:
        if not isinstance(record, NormalizedEducationRecord):
            raise TypeError("education_records must contain normalized records")
        if record.source_type is not SourceType.LINKEDIN:
            continue
        entity = ResearchEntityIdentity(
            entity_id=record.education_id,
            entity_type=ResearchEntityType.COLLEGE,
            name=record.school_name,
            provider_id=record.school_id,
            linkedin_url=record.school_linkedin_url,
            source_ref=record.source_ref,
            evidence_refs=record.evidence_refs,
            provenance_refs=record.provenance_refs,
        )
        _append_unique(entities, seen_ids, entity)

    return tuple(entities)


def _append_unique(
    entities: list[ResearchEntityIdentity],
    seen_ids: set[str],
    entity: ResearchEntityIdentity,
) -> None:
    if entity.entity_id in seen_ids:
        raise ValueError(f"duplicate research entity_id: {entity.entity_id}")
    seen_ids.add(entity.entity_id)
    entities.append(entity)
