from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import (
    ContractModel,
    ReviewReason,
    WorkflowStatus,
    new_id,
    utc_now,
)


class GateResult(ContractModel):
    gate_id: str = Field(default_factory=new_id)

    name: str

    passed: bool

    requirement_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    rationale: str

    configuration_ref: str


class ReviewRequest(ContractModel):
    review_id: str = Field(default_factory=new_id)

    reason: ReviewReason

    blocking: bool

    evidence_refs: tuple[str, ...] = ()
    contradiction_refs: tuple[str, ...] = ()

    requested_action: str

    created_at: datetime = Field(default_factory=utc_now)


class PolicyResult(ContractModel):
    screening_id: str

    gates: tuple[GateResult, ...]

    review_requests: tuple[ReviewRequest, ...]

    workflow_status: WorkflowStatus

    suitability_eligible: bool

    confidence_level: str

    configuration_ref: str

    created_at: datetime = Field(default_factory=utc_now)