from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field,model_validator

from .common import (
    ContractModel,
    ContradictionStatus,
    EvidenceConfidence,
    EvidenceStatus,
    Provenance,
    SourceReliability,
    new_id,
    utc_now,
)


class Evidence(ContractModel):
    evidence_id: str = Field(default_factory=new_id)

    claim_id: str | None = None
    dimension: str | None = None

    status: EvidenceStatus
    content: dict[str, Any] | str

    provenance_refs: tuple[str, ...]
    confidence: EvidenceConfidence

    source_reliability: SourceReliability

    supports_claim: bool

    notes: str | None = None

    created_at: datetime = Field(default_factory=utc_now)


class EvidenceBundle(ContractModel):
    evidence_refs: tuple[str, ...] = ()
    provenances: tuple[Provenance, ...] = ()
    evidence: tuple[Evidence, ...] = ()


class Claim(ContractModel):
    claim_id: str = Field(default_factory=new_id)

    subject: str
    predicate: str
    value: str

    provenance_refs: tuple[str, ...]

    created_at: datetime = Field(default_factory=utc_now)


class ClaimReconciliation(ContractModel):
    claim_id: str

    contradiction_status: ContradictionStatus

    supporting_evidence_refs: tuple[str, ...] = ()
    contradicting_evidence_refs: tuple[str, ...] = ()

    rationale: str

    created_at: datetime = Field(default_factory=utc_now)

@model_validator(mode="after")
def validate_support_direction(self) -> "Evidence":
    if self.status in {
        EvidenceStatus.CONTRADICTED,
        EvidenceStatus.NOT_FOUND,
        EvidenceStatus.NOT_AUTHORIZED,
        EvidenceStatus.UNAVAILABLE,
        EvidenceStatus.NOT_APPLICABLE,
    } and self.supports_claim:
        raise ValueError(
            f"{self.status} evidence cannot support a claim"
        )

    if self.status in {
        EvidenceStatus.SUPPORTED,
        EvidenceStatus.PARTIALLY_SUPPORTED,
    } and not self.supports_claim:
        raise ValueError(
            f"{self.status} evidence must support a claim"
        )

    return self