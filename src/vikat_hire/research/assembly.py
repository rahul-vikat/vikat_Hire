from __future__ import annotations

from collections.abc import Iterable

from vikat_hire.contracts.research import (
    COLLEGE_DIMENSIONS,
    COMPANY_DIMENSIONS,
    AssembledResearchEvidence,
    AuditedResearchObservation,
    ResearchDimension,
    ResearchDimensionEvidence,
    ResearchEntityIdentity,
    ResearchEntityType,
    ResearchEvidenceAssembly,
    ResearchFilterStatus,
)

from ._ids import deterministic_id


class ResearchEvidenceAssemblyError(ValueError):
    """Invalid inputs to pure research evidence assembly."""


def assemble_research_evidence(
    *,
    entities: Iterable[ResearchEntityIdentity],
    observations: Iterable[AuditedResearchObservation],
) -> tuple[ResearchEvidenceAssembly, ...]:
    """Group accepted evidence and retain every observation for audit."""
    entity_tuple = tuple(entities)
    observation_tuple = tuple(observations)
    if any(not isinstance(item, ResearchEntityIdentity) for item in entity_tuple):
        raise ResearchEvidenceAssemblyError("entities must contain ResearchEntityIdentity objects")
    if any(not isinstance(item, AuditedResearchObservation) for item in observation_tuple):
        raise ResearchEvidenceAssemblyError(
            "observations must contain AuditedResearchObservation objects"
        )

    entity_by_id = {entity.entity_id: entity for entity in entity_tuple}
    if len(entity_by_id) != len(entity_tuple):
        raise ResearchEvidenceAssemblyError("duplicate research entity_id")
    observation_ids = [item.observation_id for item in observation_tuple]
    if len(observation_ids) != len(set(observation_ids)):
        raise ResearchEvidenceAssemblyError("duplicate observation_id")

    for observation in observation_tuple:
        entity = entity_by_id.get(observation.entity.entity_id)
        if entity is None:
            raise ResearchEvidenceAssemblyError("observation references an unknown research entity")
        if entity != observation.entity:
            raise ResearchEvidenceAssemblyError(
                "observation entity identity does not match assembly input"
            )
        if observation.result.entity_type is not entity.entity_type:
            raise ResearchEvidenceAssemblyError(
                "observation result entity_type does not match entity"
            )
        if observation.result.dimension not in _dimensions_for(entity.entity_type):
            raise ResearchEvidenceAssemblyError(
                "observation dimension does not belong to entity type"
            )

    ordered_entities = sorted(
        entity_tuple,
        key=lambda entity: (
            entity.entity_type.value,
            entity.name.casefold(),
            entity.entity_id,
        ),
    )
    assemblies: list[ResearchEvidenceAssembly] = []
    for entity in ordered_entities:
        entity_observations = tuple(
            sorted(
                (item for item in observation_tuple if item.entity.entity_id == entity.entity_id),
                key=lambda item: (
                    item.result.dimension.value,
                    item.result.result_index,
                    item.result.result_id,
                ),
            )
        )
        dimension_groups: list[ResearchDimensionEvidence] = []
        for dimension in _dimensions_for(entity.entity_type):
            accepted = tuple(
                AssembledResearchEvidence(
                    result_id=item.result.result_id,
                    observation_id=item.observation_id,
                    validation_decision_id=item.validation.decision_id,
                    relevance_decision_id=item.relevance.decision_id,
                    provenance_refs=item.provenance_refs,
                )
                for item in entity_observations
                if item.result.dimension is dimension
                and item.status is ResearchFilterStatus.ACCEPTED
            )
            dimension_groups.append(
                ResearchDimensionEvidence(
                    dimension=dimension,
                    accepted_evidence=accepted,
                )
            )
        assemblies.append(
            ResearchEvidenceAssembly(
                assembly_id=(
                    "research-assembly-"
                    + deterministic_id(
                        "research-assembly",
                        entity.entity_id,
                        *[item.observation_id for item in entity_observations],
                    )
                ),
                entity=entity,
                dimensions=tuple(dimension_groups),
                audited_observations=entity_observations,
                provenance_refs=tuple(
                    dict.fromkeys(
                        (
                            *entity.provenance_refs,
                            *(
                                provenance_ref
                                for item in entity_observations
                                for provenance_ref in item.provenance_refs
                            ),
                        )
                    )
                ),
            )
        )
    return tuple(assemblies)


def _dimensions_for(
    entity_type: ResearchEntityType,
) -> tuple[ResearchDimension, ...]:
    return COMPANY_DIMENSIONS if entity_type is ResearchEntityType.COMPANY else COLLEGE_DIMENSIONS
