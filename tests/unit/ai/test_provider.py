from __future__ import annotations

from typing import get_type_hints

from vikat_hire.ai import ExplanationProvider
from vikat_hire.contracts.explanation import (
    ExplanationContext,
    ExplanationResult,
)


class FakeExplanationProvider:
    def __init__(self, result: ExplanationResult) -> None:
        self.result = result
        self.received_context: ExplanationContext | None = None

    def __call__(
        self,
        context: ExplanationContext,
    ) -> ExplanationResult:
        self.received_context = context
        return self.result


def test_explanation_provider_protocol_exposes_expected_call_contract() -> None:
    annotations = get_type_hints(ExplanationProvider.__call__)

    assert annotations["context"] is ExplanationContext
    assert annotations["return"] is ExplanationResult


def test_concrete_provider_satisfies_runtime_call_shape() -> None:
    provider = FakeExplanationProvider

    assert callable(provider)