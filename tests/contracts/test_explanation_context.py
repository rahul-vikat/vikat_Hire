from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.ai.explanation import (
    ExplanationAssemblyError,
    assemble_explanation_context,
)
from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    InputKind,
)
from vikat_hire.contracts.evaluation import (
    DimensionEvaluation,
    EvaluationResult,
)
from vikat_hire.contracts.explanation import ExplanationContext
from vikat_hire.contracts.policy import PolicyResult
from vikat_hire.contracts.scoring import ScoreResult
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.evaluation.dimensions import assemble_evaluation_result


def _evaluation(screening_id: str) -> EvaluationResult:
    dimension = DimensionEvaluation(
        dimension=DimensionName.MUST_HAVE_COVERAGE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("90"),
        rationale="Mandatory requirements are strongly supported.",
    )

    return assemble_evaluation_result(
        screening_id=screening_id,
        dimensions=(dimension,),
    )


def _state() -> ScreeningState:
    screening_input = ScreeningInput(
        screening_id="screening-1",
        jd=DocumentInput(
            kind=InputKind.JD,
            filename="job-description.pdf",
            media_type="application/pdf",
            content_hash="jd-hash",
            storage_ref="storage://jd",
        ),
        resume=DocumentInput(
            kind=InputKind.RESUME,
            filename="resume.pdf",
            media_type="application/pdf",
            content_hash="resume-hash",
            storage_ref="storage://resume",
        ),
    )

    return ScreeningState(
        screening_id="screening-1",
        screening_input=screening_input,
    )


def test_explanation_context_accepts_matching_artifacts() -> None:
    state = _state()

    evaluation = _evaluation(state.screening_id)

    result = ExplanationContext(
        screening_id=state.screening_id,
        evaluation=evaluation,
    )

    assert result.screening_id == state.screening_id
    assert result.evaluation is evaluation
    assert result.score is None
    assert result.policy is None


def test_explanation_context_rejects_evaluation_from_another_screening() -> None:
    with pytest.raises(
        ValueError,
        match="evaluation screening_id does not match",
    ):
        ExplanationContext(
            screening_id="screening-1",
            evaluation=_evaluation("screening-2"),
        )


def test_explanation_context_rejects_score_from_another_screening() -> None:
    evaluation = _evaluation("screening-1")

    score = ScoreResult(
        screening_id="screening-2",
        dimensions=(),
        applicable_weight_total=Decimal("0"),
        score=None,
        audit=(),
    )

    with pytest.raises(
        ValueError,
        match="score screening_id does not match",
    ):
        ExplanationContext(
            screening_id="screening-1",
            evaluation=evaluation,
            score=score,
        )


def test_explanation_context_rejects_policy_from_another_screening() -> None:
    evaluation = _evaluation("screening-1")

    policy = PolicyResult(
        screening_id="screening-2",
        gates=(),
        review_requests=(),
        workflow_status="completed",
        suitability_eligible=True,
        confidence_level="high",
        configuration_ref="policy-test",
    )

    with pytest.raises(
        ValueError,
        match="policy screening_id does not match",
    ):
        ExplanationContext(
            screening_id="screening-1",
            evaluation=evaluation,
            policy=policy,
        )


def test_assembly_requires_evaluation() -> None:
    state = _state()

    with pytest.raises(
        ExplanationAssemblyError,
        match="requires completed evaluation",
    ):
        assemble_explanation_context(state)


def test_assembly_preserves_authoritative_artifacts() -> None:
    state = _state()
    evaluation = _evaluation(state.screening_id)

    state = state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )

    context = assemble_explanation_context(state)

    assert context.screening_id == state.screening_id
    assert context.evaluation is state.evaluation
    assert context.score is state.score
    assert context.policy is state.policy


def test_assembly_does_not_recalculate_evaluation() -> None:
    state = _state()
    evaluation = _evaluation(state.screening_id)

    state = state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )

    context = assemble_explanation_context(state)

    assert context.evaluation.dimensions == evaluation.dimensions
    assert context.evaluation.contradiction_refs == evaluation.contradiction_refs
    assert context.evaluation.deterministic is True


def test_assembly_rejects_mismatched_state_evaluation() -> None:
    state = _state()

    state = state.model_copy(
        update={
            "evaluation": _evaluation("screening-2"),
        }
    )

    with pytest.raises(
        ExplanationAssemblyError,
        match="evaluation screening_id does not match",
    ):
        assemble_explanation_context(state)