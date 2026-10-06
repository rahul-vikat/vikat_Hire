from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_VERSION = "vikat_hire.schema_v1"


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContractModel(BaseModel):
    """Base for immutable, strictly validated contracts."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class SourceType(StrEnum):
    JD_FILE = "jd_file"
    RESUME_FILE = "resume_file"
    CANDIDATE_INPUT = "candidate_input"
    LINKEDIN = "linkedin"
    GITHUB = "github"
    PORTFOLIO = "portfolio"
    SEARXNG = "searxng"
    MODEL = "model"
    RULE = "rule"
    HUMAN_REVIEW = "human_review"


class AccessStatus(StrEnum):
    AUTHORIZED = "authorized"
    PUBLIC = "public"
    NOT_AUTHORIZED = "not_authorized"
    UNAVAILABLE = "unavailable"


class EvidenceStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    NOT_FOUND = "not_found"
    NOT_AUTHORIZED = "not_authorized"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class EvidenceConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceReliability(StrEnum):
    PRIMARY = "primary"
    OFFICIAL = "official"
    REPUTABLE_SECONDARY = "reputable_secondary"
    SELF_REPORTED = "self_reported"
    INFERRED = "inferred"


class DerivationMethod(StrEnum):
    PARSER = "parser"
    OCR = "ocr"
    RULE = "rule"
    API = "api"
    CRAWLER = "crawler"
    DETERMINISTIC_MATCH = "deterministic_match"
    EMBEDDING = "embedding"
    LLM = "llm"
    HUMAN = "human"


class Provenance(ContractModel):
    schema_version: str = SCHEMA_VERSION
    provenance_id: str = Field(default_factory=new_id)

    source_type: SourceType
    source_ref: str | None = None
    source_uri: str | None = None

    retrieved_at: datetime | None = None
    observed_at: datetime | None = None

    locator: dict[str, str] | None = None
    excerpt: str | None = None
    content_hash: str | None = None

    method: DerivationMethod
    model_config_ref: str | None = None

    access_status: AccessStatus

    created_at: datetime = Field(default_factory=utc_now)


class AuditRef(ContractModel):
    """Reference used to connect derived objects to their inputs."""

    object_id: str
    object_type: str


class Confidence(ContractModel):
    """Confidence in an observation/evaluation, not candidate suitability."""

    level: EvidenceConfidence
    rationale: str
    provenance_refs: tuple[str, ...] = ()

    @field_validator("rationale")
    @classmethod
    def rationale_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("confidence rationale must not be blank")
        return value


class DatePrecision(StrEnum):
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"


class ApplicabilityStatus(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    NOT_EVALUATED = "not_evaluated"


class DimensionResolution(StrEnum):
    EVALUATED = "evaluated"
    EXCLUDED = "excluded"


class ExclusionReason(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    NOT_FOUND = "not_found"
    NOT_AUTHORIZED = "not_authorized"
    UNAVAILABLE = "unavailable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RequirementImportance(StrEnum):
    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"
    INFORMATIONAL = "informational"


class RequirementCategory(StrEnum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    RESPONSIBILITY = "responsibility"
    LOCATION = "location"
    AVAILABILITY = "availability"
    OTHER = "other"


class MatchStatus(StrEnum):
    MATCHED = "matched"
    PARTIAL = "partial"
    NOT_MATCHED = "not_matched"
    UNRESOLVED = "unresolved"


class ContradictionStatus(StrEnum):
    NONE = "none"
    SUSPECTED = "suspected"
    VALIDATED = "validated"


class WorkflowStatus(StrEnum):
    CREATED = "created"
    WAITING_FOR_INPUT = "waiting_for_input"
    COLLECTING = "collecting"
    NORMALIZING = "normalizing"
    EVALUATING = "evaluating"
    REVIEW_REQUIRED = "review_required"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewReason(StrEnum):
    MISSING_REQUIRED_INPUT = "missing_required_input"
    AMBIGUOUS_REQUIREMENT = "ambiguous_requirement"
    CONTRADICTION = "contradiction"
    AUTHORIZATION = "authorization"
    UNCERTAIN_EVIDENCE = "uncertain_evidence"
    BORDERLINE_POLICY = "borderline_policy"
    SYSTEM_FAILURE = "system_failure"


class InputKind(StrEnum):
    JD = "jd"
    RESUME = "resume"
    LINKEDIN = "linkedin"
    GITHUB = "github"
    PORTFOLIO = "portfolio"


class DimensionName(StrEnum):
    MUST_HAVE_COVERAGE = "must_have_coverage"
    JD_ALIGNED_EXPERIENCE = "jd_aligned_experience"
    SEMANTIC_FIT = "semantic_fit"
    SENIORITY_SCOPE_ALIGNMENT = "seniority_scope_alignment"
    NICE_TO_HAVE_COVERAGE = "nice_to_have_coverage"
    LINKEDIN_EVIDENCE = "linkedin_evidence"
    GITHUB_EVIDENCE = "github_evidence"
    PORTFOLIO_EVIDENCE = "portfolio_evidence"


def validate_percentage(value: Decimal) -> Decimal:
    if value < Decimal("0") or value > Decimal("100"):
        raise ValueError("percentage must be between 0 and 100")
    return value


def validate_score(value: Decimal) -> Decimal:
    return validate_percentage(value)