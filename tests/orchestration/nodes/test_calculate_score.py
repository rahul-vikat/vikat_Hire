from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    InputKind,
)
from vikat_hire.contracts.evaluation import (
    DimensionEvaluation,
    EvaluationResult,
)
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.nodes.calculate_score import (
    ScoreCalculationNodeError,
    calculate_score_node,
)


SCORING_RELEASE = "verifyhire-scoring@2.2.0"


def _screening_input() -> ScreeningInput:
    return ScreeningInput(
        jd=DocumentInput(
            kind=InputKind.JD,
            filename="job-description.txt",
            media_type="text/plain",
            content_hash="jd-content-hash",
            storage_ref="test://job-description",
        ),
        resume=DocumentInput(
            kind=InputKind.RESUME,
            filename="resume.txt",
            media_type="text/plain",
            content_hash="resume-content-hash",
            storage_ref="test://resume",
        ),
    )


def _state_with_evaluation() -> ScreeningState:
    screening_input = _screening_input()

    state = ScreeningState(
        screening_id=screening_input.screening_id,
        screening_input=screening_input,
    )

    evaluation = EvaluationResult(
        screening_id=state.screening_id,
        dimensions=(
            DimensionEvaluation(
                dimension=DimensionName.MUST_HAVE_COVERAGE,
                applicability=ApplicabilityStatus.APPLICABLE,
                resolution=DimensionResolution.EVALUATED,
                raw_value=Decimal("80"),
                evidence_refs=("evidence-1",),
                requirement_refs=("requirement-1",),
                provenance_refs=("provenance-1",),
                rationale="Deterministically evaluated must-have coverage.",
            ),
        ),
        deterministic=True,
    )

    return state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )


def test_calculate_score_node_attaches_authoritative_score() -> None:
    state = _state_with_evaluation()

    result = calculate_score_node(
        state,
        scoring_release=SCORING_RELEASE,
    )

    assert result.score is not None
    assert result.score.screening_id == state.screening_id
    assert result.score.score == Decimal("80.00")
    assert result.score.applicable_weight_total == Decimal("30")


def test_calculate_score_node_preserves_evaluation() -> None:
    state = _state_with_evaluation()

    result = calculate_score_node(
        state,
        scoring_release=SCORING_RELEASE,
    )

    assert result.evaluation == state.evaluation


def test_calculate_score_node_preserves_unrelated_state() -> None:
    state = _state_with_evaluation().model_copy(
        update={
            "required_inputs_missing": ("linkedin_url",),
            "errors": ("existing-error",),
            "revision": 7,
        }
    )

    result = calculate_score_node(
        state,
        scoring_release=SCORING_RELEASE,
    )

    assert result.required_inputs_missing == state.required_inputs_missing
    assert result.errors == state.errors
    assert result.revision == state.revision
    assert result.screening_input == state.screening_input
    assert result.evaluation == state.evaluation


def test_calculate_score_node_requires_evaluation() -> None:
    screening_input = _screening_input()

    state = ScreeningState(
        screening_id=screening_input.screening_id,
        screening_input=screening_input,
    )

    with pytest.raises(
        ScoreCalculationNodeError,
        match="completed evaluation",
    ):
        calculate_score_node(
            state,
            scoring_release=SCORING_RELEASE,
        )


def test_calculate_score_node_rejects_blank_release() -> None:
    state = _state_with_evaluation()

    with pytest.raises(
        ScoreCalculationNodeError,
        match="scoring_release must not be blank",
    ):
        calculate_score_node(
            state,
            scoring_release="   ",
        )


def test_calculate_score_node_rejects_mismatched_screening_id() -> None:
    state = _state_with_evaluation()

    mismatched_evaluation = state.evaluation.model_copy(
        update={
            "screening_id": "different-screening-id",
        }
    )

    state = state.model_copy(
        update={
            "evaluation": mismatched_evaluation,
        }
    )

    with pytest.raises(
        ScoreCalculationNodeError,
        match="does not match",
    ):
        calculate_score_node(
            state,
            scoring_release=SCORING_RELEASE,
        )


def test_calculate_score_node_rejects_unknown_scoring_release() -> None:
    state = _state_with_evaluation()

    with pytest.raises(
        KeyError,
        match="unknown scoring release",
    ):
        calculate_score_node(
            state,
            scoring_release="verifyhire-scoring@unknown",
        )


def test_calculate_score_node_preserves_excluded_dimensions() -> None:
    state = _state_with_evaluation()

    evaluation = state.evaluation.model_copy(
        update={
            "dimensions": (
                state.evaluation.dimensions[0],
                DimensionEvaluation(
                    dimension=DimensionName.GITHUB_EVIDENCE,
                    applicability=ApplicabilityStatus.APPLICABLE,
                    resolution=DimensionResolution.EXCLUDED,
                    exclusion_reason=ExclusionReason.NOT_AUTHORIZED,
                    evidence_refs=(),
                    requirement_refs=(),
                    provenance_refs=(),
                    rationale="GitHub evidence was not authorized.",
                ),
            )
        }
    )

    state = state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )

    result = calculate_score_node(
        state,
        scoring_release=SCORING_RELEASE,
    )

    assert result.score is not None
    assert result.score.score == Decimal("80.00")
    assert result.score.applicable_weight_total == Decimal("30")