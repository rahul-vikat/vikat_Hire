from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from .common import ContractModel, DimensionName, new_id, utc_now
from .evaluation import EvaluationResult
from .policy import PolicyResult
from .scoring import ScoreResult


class DimensionExplanation(ContractModel):
    """
    Recruiter-facing explanation for one authoritative evaluation dimension.

    This contract contains explanatory text only. It does not calculate,
    modify, or replace the deterministic dimension evaluation or score.
    """

    explanation_id: str = Field(default_factory=new_id)

    dimension: DimensionName

    summary: str

    strengths: tuple[str, ...] = ()

    gaps: tuple[str, ...] = ()

    evidence_refs: tuple[str, ...] = ()

    requirement_refs: tuple[str, ...] = ()

    provenance_refs: tuple[str, ...] = ()

    evaluation_ref: str | None = None

    @field_validator("summary")
    @classmethod
    def summary_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("dimension explanation summary must not be blank")
        return value

    @field_validator("strengths", "gaps")
    @classmethod
    def explanation_items_must_not_be_blank(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError(
                "dimension explanation items must not be blank"
            )
        return value


class ExplanationResult(ContractModel):
    """
    Complete recruiter-facing explanation.

    This is a presentation/explanation artifact. It is never an authority
    for score, eligibility, policy, or evaluation.
    """

    explanation_id: str = Field(default_factory=new_id)

    screening_id: str

    summary: str

    strengths: tuple[str, ...] = ()

    gaps: tuple[str, ...] = ()

    review_items: tuple[str, ...] = ()

    dimensions: tuple[DimensionExplanation, ...]

    evidence_refs: tuple[str, ...] = ()

    policy_refs: tuple[str, ...] = ()

    evaluation_refs: tuple[str, ...] = ()

    generated_by: str

    model_config_ref: str | None = None

    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("summary")
    @classmethod
    def summary_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("explanation summary must not be blank")
        return value

    @field_validator("strengths", "gaps", "review_items")
    @classmethod
    def result_items_must_not_be_blank(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError(
                "explanation result items must not be blank"
            )
        return value

    @field_validator("generated_by")
    @classmethod
    def generated_by_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("generated_by must not be blank")
        return value


class ExplanationContext(ContractModel):
    """
    Authoritative input assembled for explanation generation.

    This contract contains existing deterministic artifacts only.
    It does not calculate score, eligibility, evaluation, or policy.
    An explanation generator may interpret this context, but may not
    replace any authoritative artifact with model-generated values.
    """

    screening_id: str

    evaluation: EvaluationResult

    score: ScoreResult | None = None

    policy: PolicyResult | None = None

    @field_validator("screening_id")
    @classmethod
    def screening_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("explanation context screening_id must not be blank")
        return value

    @model_validator(mode="after")
    def validate_artifact_screening_ids(self) -> "ExplanationContext":
        if self.evaluation.screening_id != self.screening_id:
            raise ValueError(
                "explanation context evaluation screening_id does not match "
                "screening_id"
            )

        if (
            self.policy is not None
            and self.policy.screening_id != self.screening_id
        ):
            raise ValueError(
                "explanation context policy screening_id does not match "
                "screening_id"
            )

        if (
            self.score is not None
            and self.score.screening_id != self.screening_id
        ):
            raise ValueError(
                "explanation context score screening_id does not match "
                "screening_id"
            )

        return self