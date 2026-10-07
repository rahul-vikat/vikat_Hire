from __future__ import annotations

import pytest
from pydantic import ValidationError

from vikat_hire.contracts.common import DimensionName
from vikat_hire.contracts.explanation import (
    DimensionExplanation,
    ExplanationResult,
)


def _dimension_explanation() -> DimensionExplanation:
    return DimensionExplanation(
        dimension=DimensionName.MUST_HAVE_COVERAGE,
        summary="Most mandatory requirements are supported.",
        strengths=("Python experience is directly supported.",),
        gaps=("One required certification is not evidenced.",),
        evidence_refs=("evidence-1",),
        requirement_refs=("requirement-1",),
        provenance_refs=("provenance-1",),
        evaluation_ref="dimension-evaluation-1",
    )


def test_dimension_explanation_accepts_valid_content() -> None:
    result = _dimension_explanation()

    assert result.dimension is DimensionName.MUST_HAVE_COVERAGE
    assert result.summary == "Most mandatory requirements are supported."
    assert result.evidence_refs == ("evidence-1",)


def test_dimension_explanation_rejects_blank_summary() -> None:
    with pytest.raises(
        ValidationError,
        match="dimension explanation summary must not be blank",
    ):
        DimensionExplanation(
            dimension=DimensionName.MUST_HAVE_COVERAGE,
            summary="   ",
        )


def test_dimension_explanation_rejects_blank_items() -> None:
    with pytest.raises(
        ValidationError,
        match="dimension explanation items must not be blank",
    ):
        DimensionExplanation(
            dimension=DimensionName.MUST_HAVE_COVERAGE,
            summary="Valid summary.",
            strengths=("valid", "   "),
        )


def test_explanation_result_accepts_dimension_explanations() -> None:
    result = ExplanationResult(
        screening_id="screening-1",
        summary="Candidate is a strong overall match.",
        strengths=("Strong backend experience.",),
        gaps=("Limited evidence for one preferred skill.",),
        review_items=("Review the contradictory LinkedIn evidence.",),
        dimensions=(_dimension_explanation(),),
        evidence_refs=("evidence-1",),
        policy_refs=("policy-1",),
        evaluation_refs=("evaluation-1",),
        generated_by="deterministic-test",
    )

    assert result.screening_id == "screening-1"
    assert len(result.dimensions) == 1
    assert result.dimensions[0].dimension is DimensionName.MUST_HAVE_COVERAGE


def test_explanation_result_rejects_blank_summary() -> None:
    with pytest.raises(
        ValidationError,
        match="explanation summary must not be blank",
    ):
        ExplanationResult(
            screening_id="screening-1",
            summary="   ",
            dimensions=(_dimension_explanation(),),
            generated_by="deterministic-test",
        )


def test_explanation_result_rejects_blank_review_item() -> None:
    with pytest.raises(
        ValidationError,
        match="explanation result items must not be blank",
    ):
        ExplanationResult(
            screening_id="screening-1",
            summary="Valid summary.",
            review_items=("   ",),
            dimensions=(_dimension_explanation(),),
            generated_by="deterministic-test",
        )


def test_explanation_result_rejects_blank_generated_by() -> None:
    with pytest.raises(
        ValidationError,
        match="generated_by must not be blank",
    ):
        ExplanationResult(
            screening_id="screening-1",
            summary="Valid summary.",
            dimensions=(_dimension_explanation(),),
            generated_by="   ",
        )


def test_explanation_is_not_a_scoring_contract() -> None:
    result = ExplanationResult(
        screening_id="screening-1",
        summary="Candidate is a strong overall match.",
        dimensions=(_dimension_explanation(),),
        generated_by="deterministic-test",
    )

    assert not hasattr(result, "score")
    assert not hasattr(result, "suitability_eligible")