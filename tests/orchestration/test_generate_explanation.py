from __future__ import annotations

from decimal import Decimal

import pytest

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
from vikat_hire.contracts.explanation import ExplanationResult
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.dimensions import assemble_evaluation_result
from vikat_hire.orchestration.nodes.generate_explanation import (
    ExplanationGenerationNodeError,
    generate_explanation_node,
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


def _explanation(screening_id: str) -> ExplanationResult:
    return ExplanationResult(
        screening_id=screening_id,
        summary="Candidate strongly supports the mandatory requirements.",
        strengths=("Strong mandatory requirement coverage.",),
        gaps=("Additional evidence may be useful.",),
        review_items=(),
        dimensions=(),
        evidence_refs=(),
        policy_refs=(),
        evaluation_refs=(),
        generated_by="test-generator",
    )


def test_generate_explanation_node_attaches_result() -> None:
    state = _state()

    evaluation = _evaluation(state.screening_id)

    state = state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )

    received_context = None

    def generator(context):
        nonlocal received_context
        received_context = context
        return _explanation(state.screening_id)

    result = generate_explanation_node(
        state,
        generator=generator,
    )

    assert result.explanation is not None
    assert result.explanation.screening_id == state.screening_id
    assert result.explanation.generated_by == "test-generator"

    assert received_context is not None
    assert received_context.screening_id == state.screening_id
    assert received_context.evaluation is evaluation


def test_generate_explanation_node_requires_evaluation() -> None:
    state = _state()

    with pytest.raises(
        ExplanationGenerationNodeError,
        match="requires completed evaluation",
    ):
        generate_explanation_node(
            state,
            generator=lambda context: _explanation(
                context.screening_id
            ),
        )


def test_generate_explanation_node_rejects_invalid_generator_output() -> None:
    state = _state()

    state = state.model_copy(
        update={
            "evaluation": _evaluation(state.screening_id),
        }
    )

    with pytest.raises(
        ExplanationGenerationNodeError,
        match="must return an ExplanationResult",
    ):
        generate_explanation_node(
            state,
            generator=lambda context: "not-an-explanation",
        )


def test_generate_explanation_node_rejects_mismatched_screening() -> None:
    state = _state()

    state = state.model_copy(
        update={
            "evaluation": _evaluation(state.screening_id),
        }
    )

    with pytest.raises(
        ExplanationGenerationNodeError,
        match="explanation screening_id does not match",
    ):
        generate_explanation_node(
            state,
            generator=lambda context: _explanation("screening-2"),
        )


def test_generate_explanation_node_preserves_authoritative_artifacts() -> None:
    state = _state()

    evaluation = _evaluation(state.screening_id)

    state = state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )

    result = generate_explanation_node(
        state,
        generator=lambda context: _explanation(
            context.screening_id
        ),
    )

    assert result.evaluation is evaluation
    assert result.score is state.score
    assert result.policy is state.policy
    assert result.explanation is not None


def test_generate_explanation_node_does_not_recalculate_evaluation() -> None:
    state = _state()

    evaluation = _evaluation(state.screening_id)

    state = state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )

    result = generate_explanation_node(
        state,
        generator=lambda context: _explanation(
            context.screening_id
        ),
    )

    assert result.evaluation.dimensions == evaluation.dimensions
    assert result.evaluation.contradiction_refs == (
        evaluation.contradiction_refs
    )
    assert result.evaluation.deterministic is True