from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from pydantic import Field, field_validator, model_validator

from vikat_hire.contracts.common import ContractModel, validate_score
from vikat_hire.contracts.evidence import Claim, Evidence
from vikat_hire.contracts.matching import (
    LLMSemanticProposal,
    SemanticMatch,
)
from vikat_hire.contracts.normalization import JDRequirement


class LLMSemanticMatchingError(ValueError):
    """Raised when an LLM semantic proposal violates application invariants."""


class LLMSemanticContext(ContractModel):
    """
    Minimal authoritative context supplied to one semantic proposal request.

    The deterministic SemanticMatch is included as context only. It remains
    authoritative and must never be modified by an LLM provider.
    """

    requirement: JDRequirement

    candidate_claims: tuple[Claim, ...] = ()

    candidate_evidence: tuple[Evidence, ...] = ()

    deterministic_match: SemanticMatch

    @model_validator(mode="after")
    def validate_context(self) -> LLMSemanticContext:
        claim_ids = {
            claim.claim_id
            for claim in self.candidate_claims
        }

        if len(claim_ids) != len(self.candidate_claims):
            raise ValueError(
                "candidate claims must not contain duplicate claim IDs"
            )

        evidence_ids = {
            evidence.evidence_id
            for evidence in self.candidate_evidence
        }

        if len(evidence_ids) != len(self.candidate_evidence):
            raise ValueError(
                "candidate evidence must not contain duplicate evidence IDs"
            )

        for evidence in self.candidate_evidence:
            if (
                evidence.claim_id is not None
                and evidence.claim_id not in claim_ids
            ):
                raise ValueError(
                    "candidate evidence references unknown claim: "
                    f"{evidence.claim_id}"
                )

        if (
            self.deterministic_match.requirement_id
            != self.requirement.requirement_id
        ):
            raise ValueError(
                "deterministic semantic match requirement_id does not "
                "match the JD requirement"
            )

        if (
            self.deterministic_match.candidate_claim_id is not None
            and self.deterministic_match.candidate_claim_id not in claim_ids
        ):
            raise ValueError(
                "deterministic semantic match references unknown "
                "candidate claim: "
                f"{self.deterministic_match.candidate_claim_id}"
            )

        return self


class LLMSemanticDraft(ContractModel):
    """
    Untrusted provider output.

    Provider implementations return only proposal content. Application-owned
    metadata is deliberately absent and is added by LLMSemanticMatcher.
    """

    score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))

    candidate_claim_id: str

    rationale: str = Field(min_length=1)

    @field_validator("score")
    @classmethod
    def validate_score_value(cls, value: Decimal) -> Decimal:
        return validate_score(value)

    @field_validator("candidate_claim_id", "rationale")
    @classmethod
    def reject_blank_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class LLMSemanticProvider(Protocol):
    """
    Provider-neutral interface for one JD requirement semantic proposal.

    This interface is intentionally separate from ExplanationProvider.
    """

    def __call__(
        self,
        context: LLMSemanticContext,
    ) -> LLMSemanticDraft | None:
        ...


class LLMSemanticMatcher:
    """
    Application boundary for LLM semantic proposals.

    The matcher validates provider output and constructs the authoritative
    LLMSemanticProposal contract. It never changes SemanticMatch.
    """

    def __init__(
        self,
        *,
        provider: LLMSemanticProvider,
        model_config_ref: str,
        provenance_refs: tuple[str, ...],
    ) -> None:
        if not callable(provider):
            raise LLMSemanticMatchingError(
                "provider must be callable"
            )

        if not model_config_ref.strip():
            raise LLMSemanticMatchingError(
                "model_config_ref must not be blank"
            )

        if not provenance_refs:
            raise LLMSemanticMatchingError(
                "provenance_refs must not be empty"
            )

        if any(not reference.strip() for reference in provenance_refs):
            raise LLMSemanticMatchingError(
                "provenance_refs must not contain blank references"
            )

        if len(provenance_refs) != len(set(provenance_refs)):
            raise LLMSemanticMatchingError(
                "provenance_refs must not contain duplicates"
            )

        self._provider = provider
        self._model_config_ref = model_config_ref
        self._provenance_refs = provenance_refs

    def propose(
        self,
        *,
        requirement: JDRequirement,
        candidate_claims: Sequence[Claim],
        candidate_evidence: Sequence[Evidence],
        deterministic_match: SemanticMatch,
    ) -> LLMSemanticProposal | None:
        """
        Produce one proposal for exactly one JD requirement.

        A provider returning None means no valid proposal was produced.

        The deterministic SemanticMatch is returned unchanged by this
        operation and is never recalculated or overwritten.
        """

        context = LLMSemanticContext(
            requirement=requirement,
            candidate_claims=tuple(candidate_claims),
            candidate_evidence=tuple(candidate_evidence),
            deterministic_match=deterministic_match,
        )

        draft = self._provider(context)

        if draft is None:
            return None

        if not isinstance(draft, LLMSemanticDraft):
            raise LLMSemanticMatchingError(
                "provider must return LLMSemanticDraft or None"
            )

        self._validate_draft(
            draft=draft,
            context=context,
        )

        return LLMSemanticProposal(
            requirement_id=requirement.requirement_id,
            candidate_claim_id=draft.candidate_claim_id,
            score=draft.score,
            rationale=draft.rationale,
            model_config_ref=self._model_config_ref,
            provenance_refs=self._provenance_refs,
        )

    @staticmethod
    def _validate_draft(
        *,
        draft: LLMSemanticDraft,
        context: LLMSemanticContext,
    ) -> None:
        claim_ids = {
            claim.claim_id
            for claim in context.candidate_claims
        }

        if draft.candidate_claim_id not in claim_ids:
            raise LLMSemanticMatchingError(
                "LLM semantic proposal references unknown candidate claim: "
                f"{draft.candidate_claim_id}"
            )

        if (
            draft.score < Decimal("0")
            or draft.score > Decimal("100")
        ):
            raise LLMSemanticMatchingError(
                "LLM semantic proposal score must be between 0 and 100"
            )

        if not draft.rationale.strip():
            raise LLMSemanticMatchingError(
                "LLM semantic proposal rationale must not be blank"
            )
