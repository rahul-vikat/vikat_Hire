from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from .common import (
    ContractModel,
    DatePrecision,
    EvidenceConfidence,
    EvidenceStatus,
    RequirementCategory,
    RequirementImportance,
    SourceType,
)
from .evaluation import ExperienceRecord
from .evidence import Claim
from .scope import JDScopeEvidence, ScopeEvidence, ScopeEvidenceCategory, ScopeEvidencePolarity


class NormalizedSourceState(StrEnum):
    AVAILABLE = "available"
    NOT_FOUND = "not_found"
    NOT_AUTHORIZED = "not_authorized"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class ExtractionKind(StrEnum):
    PDF_TEXT = "pdf_text"
    DOCX_TEXT = "docx_text"
    PLAIN_TEXT = "plain_text"
    OCR_TEXT = "ocr_text"


class ExtractedTextBlock(ContractModel):
    """
    Deterministically extracted source text.

    This is an extraction artifact, not an evaluation result.
    """

    block_id: str = Field(min_length=1)

    source_type: SourceType
    source_ref: str = Field(min_length=1)

    text: str = Field(min_length=1)

    page_number: int | None = Field(default=None, ge=1)
    section: str | None = None

    extraction_kind: ExtractionKind

    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("extracted text must not be blank")
        return value

    @field_validator("section")
    @classmethod
    def section_must_not_be_blank(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("section must not be blank")
        return value


class NormalizedSkill(ContractModel):
    """
    Candidate-side normalized skill observation.

    This does not indicate whether the skill satisfies any JD requirement.
    """

    skill_id: str = Field(min_length=1)

    name: str = Field(min_length=1)

    canonical_ref: str | None = None

    source_type: SourceType
    source_ref: str = Field(min_length=1)

    evidence_status: EvidenceStatus

    evidence_refs: tuple[str, ...] = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    confidence: EvidenceConfidence

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("skill name must not be blank")
        return value


class NormalizedResponsibility(ContractModel):
    """
    Candidate-side normalized responsibility observation.

    This does not determine seniority or JD alignment.
    """

    responsibility_id: str = Field(min_length=1)

    text: str = Field(min_length=1)

    source_type: SourceType
    source_ref: str = Field(min_length=1)

    evidence_status: EvidenceStatus

    evidence_refs: tuple[str, ...] = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    confidence: EvidenceConfidence

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("responsibility text must not be blank")
        return value


class NormalizedExperienceRecord(ContractModel):
    """
    Normalization-layer experience record.

    The existing ExperienceRecord is the deterministic-evaluation input.
    This contract retains the source text needed to construct that record
    without allowing normalization to perform evaluation.
    """

    record_id: str = Field(min_length=1)

    employer: str | None = None
    role: str | None = None

    start_date: date | None = None
    end_date: date | None = None

    date_precision: DatePrecision = DatePrecision.UNKNOWN
    current: bool = False

    skill_refs: tuple[str, ...] = ()
    responsibility_refs: tuple[str, ...] = ()

    source_text: str = Field(min_length=1)

    source_type: SourceType
    source_ref: str = Field(min_length=1)

    evidence_refs: tuple[str, ...] = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("source_text")
    @classmethod
    def source_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_text must not be blank")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> NormalizedExperienceRecord:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError(
                "experience end_date cannot precede start_date"
            )

        if self.current and self.end_date is not None:
            raise ValueError(
                "current experience cannot have end_date"
            )

        return self

    def to_evaluation_record(self) -> ExperienceRecord:
        """
        Convert only the normalized factual fields into the existing
        deterministic-evaluation contract.

        No evaluation or scoring occurs here.
        """
        return ExperienceRecord(
            record_id=self.record_id,
            employer=self.employer,
            role=self.role,
            start_date=self.start_date,
            end_date=self.end_date,
            date_precision=self.date_precision,
            current=self.current,
            skill_refs=self.skill_refs,
            responsibility_refs=self.responsibility_refs,
            provenance_refs=self.provenance_refs,
            evidence_refs=self.evidence_refs,
        )


class NormalizedEducationRecord(ContractModel):
    """Factual education observation normalized from a source profile."""

    education_id: str = Field(min_length=1)
    school_name: str = Field(min_length=1)
    school_id: str | None = None
    school_linkedin_url: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    period: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    date_precision: DatePrecision = DatePrecision.UNKNOWN
    current: bool = False
    start_date: date | None = None
    end_date: date | None = None
    date_precision: DatePrecision = DatePrecision.UNKNOWN
    current: bool = False
    source_type: SourceType
    source_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("school_name")
    @classmethod
    def school_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("school_name must not be blank")
        return value.strip()


class JDRequirement(ContractModel):
    """
    One normalized JD requirement.

    This is a yardstick definition, not an evaluation result.
    """

    requirement_id: str = Field(min_length=1)

    category: RequirementCategory
    importance: RequirementImportance

    text: str = Field(min_length=1)

    canonical_refs: tuple[str, ...] = ()

    source_type: SourceType
    source_ref: str = Field(min_length=1)

    evidence_refs: tuple[str, ...] = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("JD requirement text must not be blank")
        return value


class JDExperienceRequirement(JDRequirement):
    """
    Typed JD experience requirement.

    This remains a requirement definition. It does not calculate
    candidate experience or an experience score.
    """

    category: RequirementCategory = RequirementCategory.EXPERIENCE

    minimum_years: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
    )

    @model_validator(mode="after")
    def validate_minimum_years(self) -> JDExperienceRequirement:
        if self.minimum_years == Decimal("0"):
            raise ValueError(
                "minimum_years must be positive when specified"
            )
        return self


class NormalizedClaim(ContractModel):
    """
    Normalized factual claim.

    A claim is an observation extracted from source material. It is not
    automatically considered true, matched, or sufficient.
    """

    claim: Claim

    source_type: SourceType
    source_ref: str = Field(min_length=1)

    evidence_status: EvidenceStatus

    evidence_refs: tuple[str, ...] = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    confidence: EvidenceConfidence


class NormalizedScopeEvidence(ContractModel):
    """
    Normalized candidate scope evidence.

    Deliberately contains no candidate ScopeLevel and no score.
    """

    scope_evidence: ScopeEvidence

    source_type: SourceType
    source_ref: str = Field(min_length=1)

    evidence_refs: tuple[str, ...] = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)


class NormalizedJDScopeEvidence(ContractModel):
    evidence_id: str = Field(min_length=1)
    categories: tuple[ScopeEvidenceCategory, ...] = ()
    supervision_learning: bool = False
    polarity: ScopeEvidencePolarity
    explicit_text: str = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    def to_evaluation_evidence(self) -> JDScopeEvidence:
        return JDScopeEvidence(
            evidence_id=self.evidence_id,
            categories=self.categories,
            supervision_learning=self.supervision_learning,
            polarity=self.polarity,
            explicit_text=self.explicit_text,
            provenance_refs=self.provenance_refs,
        )


class NormalizationResult(ContractModel):
    """
    Complete normalization output.

    No field in this contract represents candidate suitability,
    match score, seniority score, or final screening score.
    """

    screening_id: str = Field(min_length=1)

    extracted_blocks: tuple[ExtractedTextBlock, ...] = ()

    claims: tuple[NormalizedClaim, ...] = ()

    skills: tuple[NormalizedSkill, ...] = ()

    responsibilities: tuple[NormalizedResponsibility, ...] = ()

    experience_records: tuple[NormalizedExperienceRecord, ...] = ()

    education_records: tuple[NormalizedEducationRecord, ...] = ()

    scope_evidence: tuple[NormalizedScopeEvidence, ...] = ()

    jd_requirements: tuple[JDRequirement, ...] = ()

    jd_experience_requirements: tuple[JDExperienceRequirement, ...] = ()

    jd_scope_evidence: tuple[NormalizedJDScopeEvidence, ...] = ()

    source_states: dict[str, NormalizedSourceState] = {}

    provenance_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_source_states(self) -> NormalizationResult:
        allowed_keys = {
            source.source_ref
            for source in self.extracted_blocks
        }
        allowed_keys.update(
            source.source_ref
            for source in self.skills
        )
        allowed_keys.update(
            source.source_ref
            for source in self.responsibilities
        )
        allowed_keys.update(
            source.source_ref
            for source in self.experience_records
        )
        allowed_keys.update(
            source.source_ref
            for source in self.education_records
        )
        allowed_keys.update(
            source.source_ref
            for source in self.scope_evidence
        )
        allowed_keys.update(
            source.source_ref
            for source in self.jd_requirements
        )
        allowed_keys.update(
            source.source_ref
            for source in self.claims
        )

        # Source states can be recorded before any normalized artifact exists.
        # These prefixes are the canonical source-reference namespaces used by
        # the collection contract.
        source_ref_prefixes = (
            "jd-",
            "resume-",
            "linkedin-",
            "github-",
            "portfolio-",
        )
        allowed_keys.update(
            source_ref
            for source_ref in self.source_states
            if source_ref.startswith(source_ref_prefixes)
        )

        unknown = set(self.source_states) - allowed_keys

        if unknown:
            raise ValueError(
                "source_states contains unknown source references: "
                f"{sorted(unknown)}"
            )

        return self
