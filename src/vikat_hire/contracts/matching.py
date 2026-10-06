from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator

from .common import (
    ContractModel,
    MatchStatus,
    new_id,
    utc_now,
    validate_score,
)


class KeywordMatch(ContractModel):
    match_id: str = Field(default_factory=new_id)

    requirement_id: str
    candidate_claim_id: str | None = None

    matched_text: str | None = None
    canonical_skill_ref: str | None = None

    match_type: str
    status: MatchStatus

    score: Decimal

    provenance_refs: tuple[str, ...]

    @field_validator("score")
    @classmethod
    def score_must_be_valid(cls, value: Decimal) -> Decimal:
        return validate_score(value)


class SemanticMatch(ContractModel):
    match_id: str = Field(default_factory=new_id)

    requirement_id: str
    candidate_claim_id: str | None = None

    status: MatchStatus
    score: Decimal

    rationale: str

    provenance_refs: tuple[str, ...]

    created_at: datetime = Field(default_factory=utc_now)


class LLMSemanticProposal(ContractModel):
    """
    Display/audit proposal only.

    This contract is deliberately separate from SemanticMatch.
    It must never be accepted directly by the deterministic scorer.
    """

    proposal_id: str = Field(default_factory=new_id)

    requirement_id: str
    candidate_claim_id: str | None = None

    score: Decimal
    rationale: str

    model_config_ref: str
    provenance_refs: tuple[str, ...]

    created_at: datetime = Field(default_factory=utc_now)