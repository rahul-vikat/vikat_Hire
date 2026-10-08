from __future__ import annotations

import re
import unicodedata

from vikat_hire.config.research_relevance import RESEARCH_RELEVANCE_TERMS
from vikat_hire.contracts.research import (
    AuditedResearchObservation,
    DimensionRelevanceDecision,
    DimensionRelevanceReason,
    DimensionRelevanceStatus,
    EntityValidationDecision,
    EntityValidationStatus,
    RawResearchResult,
    ResearchEntityIdentity,
    ResearchFilterReason,
    ResearchFilterStatus,
)

from ._ids import deterministic_id


class ResearchEvidenceFilteringError(ValueError):
    """Invalid research evidence filtering input or configuration."""


def filter_research_evidence(
    *,
    entity: ResearchEntityIdentity,
    result: RawResearchResult,
    validation: EntityValidationDecision,
) -> AuditedResearchObservation:
    """Apply configured lexical relevance after entity validation."""
    if not isinstance(entity, ResearchEntityIdentity):
        raise ResearchEvidenceFilteringError("entity must be a ResearchEntityIdentity")
    if not isinstance(result, RawResearchResult):
        raise ResearchEvidenceFilteringError("result must be a RawResearchResult")
    if not isinstance(validation, EntityValidationDecision):
        raise ResearchEvidenceFilteringError("validation must be an EntityValidationDecision")
    if validation.entity_id != entity.entity_id:
        raise ResearchEvidenceFilteringError("validation entity_id does not match target")
    if validation.result_id != result.result_id:
        raise ResearchEvidenceFilteringError("validation result_id does not match result")
    if result.entity_type is not entity.entity_type:
        raise ResearchEvidenceFilteringError("research result entity_type does not match target")

    configured = RESEARCH_RELEVANCE_TERMS[entity.entity_type].get(result.dimension)
    if not configured:
        raise ResearchEvidenceFilteringError(
            "no configured relevance terms for entity type/dimension"
        )

    if validation.status is EntityValidationStatus.VALIDATED:
        text = _normalize_text(f"{result.title}\n{result.content}")
        text = _remove_identity_phrases(
            text,
            (entity.name, *entity.aliases),
        )
        matched_terms = tuple(term for term in configured if _contains_term_or_phrase(text, term))
        relevance_status = (
            DimensionRelevanceStatus.RELEVANT
            if matched_terms
            else DimensionRelevanceStatus.IRRELEVANT
        )
        relevance_reason = (
            DimensionRelevanceReason.MATCHED_CONFIGURED_TERM
            if matched_terms
            else DimensionRelevanceReason.NO_CONFIGURED_TERM_MATCH
        )
    else:
        matched_terms = ()
        relevance_status = DimensionRelevanceStatus.NOT_EVALUATED
        relevance_reason = DimensionRelevanceReason.ENTITY_NOT_VALIDATED

    relevance_id = deterministic_id(
        "dimension-relevance",
        entity.entity_id,
        result.result_id,
        validation.decision_id,
        relevance_status.value,
        *matched_terms,
    )
    relevance = DimensionRelevanceDecision(
        decision_id=f"dimension-relevance-{relevance_id}",
        entity_id=entity.entity_id,
        result_id=result.result_id,
        validation_decision_id=validation.decision_id,
        status=relevance_status,
        reason=relevance_reason,
        matched_terms=matched_terms,
        provenance_refs=tuple(
            dict.fromkeys((*validation.provenance_refs, *result.provenance_refs))
        ),
    )

    if validation.status is EntityValidationStatus.AMBIGUOUS:
        filter_status = ResearchFilterStatus.AMBIGUOUS
        filter_reason = ResearchFilterReason.ENTITY_AMBIGUOUS
    elif validation.status is EntityValidationStatus.REJECTED:
        filter_status = ResearchFilterStatus.REJECTED
        filter_reason = ResearchFilterReason.ENTITY_REJECTED
    elif relevance_status is DimensionRelevanceStatus.RELEVANT:
        filter_status = ResearchFilterStatus.ACCEPTED
        filter_reason = ResearchFilterReason.VALIDATED_AND_RELEVANT
    else:
        filter_status = ResearchFilterStatus.REJECTED
        filter_reason = ResearchFilterReason.DIMENSION_IRRELEVANT

    observation_id = deterministic_id(
        "research-observation",
        entity.entity_id,
        result.result_id,
        validation.decision_id,
        relevance.decision_id,
        filter_status.value,
        filter_reason.value,
    )
    return AuditedResearchObservation(
        observation_id=f"research-observation-{observation_id}",
        entity=entity,
        result=result,
        validation=validation,
        relevance=relevance,
        status=filter_status,
        reason=filter_reason,
        provenance_refs=tuple(
            dict.fromkeys(
                (
                    *entity.provenance_refs,
                    *result.provenance_refs,
                    *validation.provenance_refs,
                    *relevance.provenance_refs,
                )
            )
        ),
    )


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def _contains_term_or_phrase(text: str, term: str) -> bool:
    normalized = _normalize_text(term)
    if not normalized:
        raise ResearchEvidenceFilteringError("configured relevance terms must not be blank")
    return f" {normalized} " in f" {text} "


def _remove_identity_phrases(text: str, phrases: tuple[str, ...]) -> str:
    for phrase in phrases:
        normalized = _normalize_text(phrase)
        if normalized:
            text = f" {text} ".replace(
                f" {normalized} ",
                " ",
            ).strip()
    return " ".join(text.split())
