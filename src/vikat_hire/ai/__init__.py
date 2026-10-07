from __future__ import annotations

from typing import Protocol

from vikat_hire.contracts.explanation import (
    ExplanationContext,
    ExplanationResult,
)


class ExplanationProvider(Protocol):
    """
    Provider-neutral interface for generating explanations.

    Implementations may use an LLM, a deterministic generator, or another
    provider. The provider receives authoritative application artifacts and
    returns only an ExplanationResult.

    Providers must not calculate or replace evaluation, scoring, policy,
    eligibility, or other authoritative decisions.
    """

    def __call__(
        self,
        context: ExplanationContext,
    ) -> ExplanationResult:
        ...