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


COMPANY_DIMENSIONS: tuple[ResearchDimension, ...] = (
    ResearchDimension.FINANCIAL_VALUATION,
    ResearchDimension.MARKET_POSITION,
    ResearchDimension.ENGINEERING_TECHNICAL,
    ResearchDimension.REPUTATION_COMPLIANCE,
)

COLLEGE_DIMENSIONS: tuple[ResearchDimension, ...] = (
    ResearchDimension.OFFICIAL_RANKING,
    ResearchDimension.ACCREDITATION,
    ResearchDimension.ACADEMIC_RESEARCH,
    ResearchDimension.PLACEMENTS,
    ResearchDimension.PERCEPTION_INFRASTRUCTURE,
)


class EntityValidationStatus(StrEnum):
    VALIDATED = "validated"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


class EntityValidationReason(StrEnum):
    EXACT_NAME_MATCH = "exact_name_match"
    EXPLICIT_ALIAS_MATCH = "explicit_alias_match"
    EXACT_LINKEDIN_URL_MATCH = "exact_linkedin_url_match"
    CONFLICTING_IDENTITY_SIGNALS = "conflicting_identity_signals"
    SIMILAR_NAME_ONLY = "similar_name_only"
    DIFFERENT_KNOWN_ENTITY = "different_known_entity"
    INSUFFICIENT_IDENTITY = "insufficient_identity"


class IdentitySignal(StrEnum):
    TARGET_NAME = "target_name"
    EXPLICIT_ALIAS = "explicit_alias"
    LINKEDIN_URL = "linkedin_url"
    SIMILAR_NAME = "similar_name"
    OTHER_KNOWN_ENTITY = "other_known_entity"
    CONFLICTING_LINKEDIN_URL = "conflicting_linkedin_url"


class DimensionRelevanceStatus(StrEnum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    NOT_EVALUATED = "not_evaluated"


class DimensionRelevanceReason(StrEnum):
    MATCHED_CONFIGURED_TERM = "matched_configured_term"
    NO_CONFIGURED_TERM_MATCH = "no_configured_term_match"
    ENTITY_NOT_VALIDATED = "entity_not_validated"


class ResearchFilterStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


class ResearchFilterReason(StrEnum):
    VALIDATED_AND_RELEVANT = "validated_and_relevant"
    ENTITY_REJECTED = "entity_rejected"
    ENTITY_AMBIGUOUS = "entity_ambiguous"
    DIMENSION_IRRELEVANT = "dimension_irrelevant"


class ResearchEntityIdentity(ContractModel):
    """Identity signals explicitly available for one researched entity."""

    entity_id: str = Field(min_length=1)
    entity_type: ResearchEntityType
    name: str = Field(min_length=1)
    provider_id: str | None = None
    universal_name: str | None = None
    linkedin_url: str | None = None
    aliases: tuple[str, ...] = ()
    source_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> ResearchEntityIdentity:
        if not self.name.strip():
            raise ValueError("research entity name must not be blank")
        if self.provider_id is not None and not self.provider_id.strip():
            raise ValueError("provider_id must be non-blank when supplied")
        if self.universal_name is not None and not self.universal_name.strip():
            raise ValueError("universal_name must be non-blank when supplied")
        if self.linkedin_url is not None and not self.linkedin_url.strip():
            raise ValueError("linkedin_url must be non-blank when supplied")
        if any(not alias.strip() for alias in self.aliases):
            raise ValueError("research entity aliases must not be blank")
        return self


class EntityValidationDecision(ContractModel):
    decision_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    result_id: str = Field(min_length=1)
    status: EntityValidationStatus
    reason: EntityValidationReason
    matched_signals: tuple[IdentitySignal, ...] = ()
    conflicting_signals: tuple[IdentitySignal, ...] = ()
    conflicting_entity_ids: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_outcome(self) -> EntityValidationDecision:
        if self.status is EntityValidationStatus.VALIDATED:
            if not self.matched_signals:
                raise ValueError("validated identity requires a matched signal")
            if self.conflicting_signals or self.conflicting_entity_ids:
                raise ValueError("validated identity cannot have conflicting signals")
        if self.status is EntityValidationStatus.REJECTED:
            if self.reason is not EntityValidationReason.DIFFERENT_KNOWN_ENTITY:
                raise ValueError("rejected identity requires a known-entity reason")
            if not self.conflicting_entity_ids:
                raise ValueError("rejected identity requires a conflicting entity")
        if self.status is EntityValidationStatus.AMBIGUOUS:
            if self.reason not in {
                EntityValidationReason.CONFLICTING_IDENTITY_SIGNALS,
                EntityValidationReason.SIMILAR_NAME_ONLY,
                EntityValidationReason.INSUFFICIENT_IDENTITY,
            }:
                raise ValueError("ambiguous identity has an invalid reason")
        return self


class DimensionRelevanceDecision(ContractModel):
    decision_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    result_id: str = Field(min_length=1)
    validation_decision_id: str = Field(min_length=1)
    status: DimensionRelevanceStatus
    reason: DimensionRelevanceReason
    matched_terms: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_relevance(self) -> DimensionRelevanceDecision:
        if self.status is DimensionRelevanceStatus.RELEVANT:
            if (
                self.reason is not DimensionRelevanceReason.MATCHED_CONFIGURED_TERM
                or not self.matched_terms
            ):
                raise ValueError("relevant decision requires matched configured terms")
        elif self.status is DimensionRelevanceStatus.IRRELEVANT:
            if (
                self.reason is not DimensionRelevanceReason.NO_CONFIGURED_TERM_MATCH
                or self.matched_terms
            ):
                raise ValueError("irrelevant decision cannot contain matched terms")
        elif self.reason is not DimensionRelevanceReason.ENTITY_NOT_VALIDATED or self.matched_terms:
            raise ValueError("unevaluated relevance requires an unvalidated entity")
        return self


class AuditedResearchObservation(ContractModel):
    observation_id: str = Field(min_length=1)
    entity: ResearchEntityIdentity
    result: RawResearchResult
    validation: EntityValidationDecision
    relevance: DimensionRelevanceDecision
    status: ResearchFilterStatus
    reason: ResearchFilterReason
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision_chain(self) -> AuditedResearchObservation:
        if self.validation.entity_id != self.entity.entity_id:
            raise ValueError("validation decision entity_id does not match")
        if self.validation.result_id != self.result.result_id:
            raise ValueError("validation decision result_id does not match")
        if self.relevance.entity_id != self.entity.entity_id:
            raise ValueError("relevance decision entity_id does not match")
        if self.relevance.result_id != self.result.result_id:
            raise ValueError("relevance decision result_id does not match")
        if self.relevance.validation_decision_id != self.validation.decision_id:
            raise ValueError("relevance decision does not reference validation")
        if not set(self.result.provenance_refs).issubset(self.provenance_refs):
            raise ValueError("observation must preserve raw result provenance")
        if self.status is ResearchFilterStatus.ACCEPTED:
            if (
                self.validation.status is not EntityValidationStatus.VALIDATED
                or self.relevance.status is not DimensionRelevanceStatus.RELEVANT
                or self.reason is not ResearchFilterReason.VALIDATED_AND_RELEVANT
            ):
                raise ValueError("accepted evidence must be validated and relevant")
        elif self.status is ResearchFilterStatus.AMBIGUOUS:
            if (
                self.validation.status is not EntityValidationStatus.AMBIGUOUS
                or self.reason is not ResearchFilterReason.ENTITY_AMBIGUOUS
            ):
                raise ValueError("ambiguous observation requires ambiguous identity")
        elif self.validation.status is EntityValidationStatus.REJECTED:
            if self.reason is not ResearchFilterReason.ENTITY_REJECTED:
                raise ValueError("rejected identity must retain rejection reason")
        elif (
            self.validation.status is not EntityValidationStatus.VALIDATED
            or self.relevance.status is not DimensionRelevanceStatus.IRRELEVANT
            or self.reason is not ResearchFilterReason.DIMENSION_IRRELEVANT
        ):
            raise ValueError("rejected evidence must be irrelevant or entity-rejected")
        return self


class AssembledResearchEvidence(ContractModel):
    result_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    validation_decision_id: str = Field(min_length=1)
    relevance_decision_id: str = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)


class ResearchDimensionEvidence(ContractModel):
    dimension: ResearchDimension
    accepted_evidence: tuple[AssembledResearchEvidence, ...] = ()


class ResearchEvidenceAssembly(ContractModel):
    assembly_id: str = Field(min_length=1)
    entity: ResearchEntityIdentity
    dimensions: tuple[ResearchDimensionEvidence, ...]
    audited_observations: tuple[AuditedResearchObservation, ...] = ()
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assembly(self) -> ResearchEvidenceAssembly:
        expected = (
            COMPANY_DIMENSIONS
            if self.entity.entity_type is ResearchEntityType.COMPANY
            else COLLEGE_DIMENSIONS
        )
        actual = tuple(item.dimension for item in self.dimensions)
        if actual != expected:
            raise ValueError(
                "assembly must contain every entity dimension exactly once in canonical order"
            )
        observation_by_result = {item.result.result_id: item for item in self.audited_observations}
        if len(observation_by_result) != len(self.audited_observations):
            raise ValueError("assembly contains duplicate result observations")
        for observation in self.audited_observations:
            if observation.entity.entity_id != self.entity.entity_id:
                raise ValueError("assembly observation belongs to another entity")
            if observation.result.entity_type is not self.entity.entity_type:
                raise ValueError("assembly observation has a mismatched entity type")
            if observation.result.dimension not in expected:
                raise ValueError("assembly observation has a mismatched dimension")
        required_provenance = set(self.entity.provenance_refs)
        for observation in self.audited_observations:
            required_provenance.update(observation.provenance_refs)
        if not required_provenance.issubset(self.provenance_refs):
            raise ValueError("assembly must preserve all observation provenance")
        for group in self.dimensions:
            seen: set[str] = set()
            for evidence in group.accepted_evidence:
                if evidence.result_id in seen:
                    raise ValueError("dimension contains duplicate accepted evidence")
                seen.add(evidence.result_id)
                observation = observation_by_result.get(evidence.result_id)
                if observation is None:
                    raise ValueError("accepted evidence has no audited observation")
                if observation.result.dimension is not group.dimension:
                    raise ValueError("accepted evidence dimension does not match")
                if observation.status is not ResearchFilterStatus.ACCEPTED:
                    raise ValueError("only accepted observations can be assembled")
        return self


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

    @model_validator(mode="after")
    def validate_dimension_type(self) -> RawResearchResult:
        dimensions = (
            COMPANY_DIMENSIONS
            if self.entity_type is ResearchEntityType.COMPANY
            else COLLEGE_DIMENSIONS
        )
        if self.dimension not in dimensions:
            raise ValueError("research dimension does not match entity_type")
        return self


class ResearchSearchBatch(ContractModel):
    entity_type: ResearchEntityType
    entity_name: str = Field(min_length=1)
    dimension: ResearchDimension
    query: str = Field(min_length=1)
    results: tuple[RawResearchResult, ...] = ()
    provenances: tuple[Provenance, ...] = ()

    @model_validator(mode="after")
    def validate_results_and_provenance(self) -> ResearchSearchBatch:
        known_provenance_ids = {provenance.provenance_id for provenance in self.provenances}
        result_ids: set[str] = set()
        for result in self.results:
            if result.result_id in result_ids:
                raise ValueError(f"duplicate raw research result ID: {result.result_id}")
            result_ids.add(result.result_id)
            if (
                result.entity_type is not self.entity_type
                or result.entity_name != self.entity_name
                or result.dimension is not self.dimension
                or result.query != self.query
            ):
                raise ValueError("raw research result context does not match its batch")
            missing = set(result.provenance_refs) - known_provenance_ids
            if missing:
                raise ValueError(
                    f"raw research result contains unknown provenance refs: {sorted(missing)}"
                )
        return self
