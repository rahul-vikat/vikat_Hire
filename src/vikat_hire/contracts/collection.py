from __future__ import annotations

from pydantic import Field, model_validator

from .common import AccessStatus, ContractModel, Provenance, SourceType


class CollectionStatus(str):
    COLLECTED = "collected"
    NOT_APPLICABLE = "not_applicable"
    NOT_AUTHORIZED = "not_authorized"


class CollectedSource(ContractModel):
    source_type: SourceType
    source_ref: str = Field(min_length=1)
    source_uri: str | None = None
    access_status: AccessStatus | None = None
    status: str
    provenance_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_state(self) -> "CollectedSource":
        if self.status == CollectionStatus.COLLECTED and self.access_status not in {AccessStatus.AUTHORIZED, AccessStatus.PUBLIC}:
            raise ValueError("collected source must have authorized or public access")
        if self.status == CollectionStatus.NOT_AUTHORIZED and self.access_status is not AccessStatus.NOT_AUTHORIZED:
            raise ValueError("not_authorized collection must have NOT_AUTHORIZED access status")
        if self.status == CollectionStatus.NOT_APPLICABLE and self.access_status is not None:
            raise ValueError("not_applicable collection must have no access status")
        if self.status in {CollectionStatus.COLLECTED, CollectionStatus.NOT_AUTHORIZED} and not self.provenance_refs:
            raise ValueError("available or unauthorized source must have provenance references")
        if self.status not in {CollectionStatus.COLLECTED, CollectionStatus.NOT_AUTHORIZED, CollectionStatus.NOT_APPLICABLE}:
            raise ValueError(f"unsupported collection status: {self.status}")
        return self

    @property
    def is_available_for_downstream_collection(self) -> bool:
        return self.status == CollectionStatus.COLLECTED


class CollectionResult(ContractModel):
    screening_id: str
    sources: tuple[CollectedSource, ...]
    provenances: tuple[Provenance, ...]

    @model_validator(mode="after")
    def validate_provenance_references(self) -> "CollectionResult":
        known = {provenance.provenance_id for provenance in self.provenances}
        for source in self.sources:
            missing = set(source.provenance_refs) - known
            if missing:
                raise ValueError(f"source contains unknown provenance references: {sorted(missing)}")
        return self

    @property
    def collected_sources(self) -> tuple[CollectedSource, ...]:
        return tuple(source for source in self.sources if source.status == CollectionStatus.COLLECTED)

    @property
    def unavailable_sources(self) -> tuple[CollectedSource, ...]:
        return tuple(source for source in self.sources if source.status in {CollectionStatus.NOT_AUTHORIZED, CollectionStatus.NOT_APPLICABLE})
