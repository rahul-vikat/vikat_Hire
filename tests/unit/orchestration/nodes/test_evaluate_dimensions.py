from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    InputKind,
)
from vikat_hire.contracts.evaluation import DimensionEvaluation
from vikat_hire.contracts.inputs import (
    DocumentInput,
    ScreeningInput,
)
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.nodes.evaluate_dimensions import (
    DimensionEvaluationNodeError,
    evaluate_dimensions_node,
)


def _state() -> ScreeningState:
    return ScreeningState(
        screening_input=ScreeningInput(
            jd=DocumentInput(
                kind=InputKind.JD,
                filename="jd.pdf",
                media_type="application/pdf",
                content_hash="jd-hash",
                storage_ref="jd-ref",
            ),
            resume=DocumentInput(
                kind=InputKind.RESUME,
                filename="resume.pdf",
                media_type="application/pdf",
                content_hash="resume-hash",
                storage_ref="resume-ref",
            ),
        )
    )


def _dimension(
    dimension: DimensionName,
    raw_value: str,
) -> DimensionEvaluation:
    return DimensionEvaluation(
        dimension=dimension,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal(raw_value),
        rationale=f"Deterministic evaluation for {dimension.value}.",
    )


def test_evaluate_dimensions_node_assembles_evaluation() -> None:
    state = _state()

    dimensions = (
        _dimension(
            DimensionName.SEMANTIC_FIT,
            "80",
        ),
        _dimension(
            DimensionName.MUST_HAVE_COVERAGE,
            "90",
        ),
    )

    result = evaluate_dimensions_node(
        state,
        dimensions=dimensions,
    )

    assert result.evaluation is not None
    assert result.evaluation.screening_id == state.screening_id
    assert result.evaluation.deterministic is True
    assert tuple(
        dimension.dimension
        for dimension in result.evaluation.dimensions
    ) == (
        DimensionName.MUST_HAVE_COVERAGE,
        DimensionName.SEMANTIC_FIT,
    )


def test_evaluate_dimensions_node_preserves_dimension_values() -> None:
    state = _state()

    dimensions = (
        _dimension(
            DimensionName.SEMANTIC_FIT,
            "73.25",
        ),
    )

    result = evaluate_dimensions_node(
        state,
        dimensions=dimensions,
    )

    assert result.evaluation is not None
    assert result.evaluation.dimensions[0].raw_value == Decimal("73.25")


def test_evaluate_dimensions_node_preserves_contradiction_refs() -> None:
    state = _state()

    result = evaluate_dimensions_node(
        state,
        dimensions=(
            _dimension(
                DimensionName.SEMANTIC_FIT,
                "80",
            ),
        ),
        contradiction_refs=("evidence-1", "evidence-2"),
    )

    assert result.evaluation is not None
    assert result.evaluation.contradiction_refs == (
        "evidence-1",
        "evidence-2",
    )


def test_evaluate_dimensions_node_rejects_duplicate_dimensions() -> None:
    state = _state()

    dimension = _dimension(
        DimensionName.SEMANTIC_FIT,
        "80",
    )

    with pytest.raises(
        DimensionEvaluationNodeError,
        match="duplicate dimension evaluation",
    ):
        evaluate_dimensions_node(
            state,
            dimensions=(dimension, dimension),
        )


def test_evaluate_dimensions_node_rejects_invalid_dimension_type() -> None:
    state = _state()

    with pytest.raises(
        DimensionEvaluationNodeError,
        match="DimensionEvaluation",
    ):
        evaluate_dimensions_node(
            state,
            dimensions=("invalid",),  # type: ignore[arg-type]
        )


def test_evaluate_dimensions_node_rejects_blank_contradiction_ref() -> None:
    state = _state()

    with pytest.raises(
        DimensionEvaluationNodeError,
        match="contradiction_refs",
    ):
        evaluate_dimensions_node(
            state,
            dimensions=(
                _dimension(
                    DimensionName.SEMANTIC_FIT,
                    "80",
                ),
            ),
            contradiction_refs=(" ",),
        )


def test_evaluate_dimensions_node_rejects_duplicate_contradiction_refs() -> None:
    state = _state()

    with pytest.raises(
        DimensionEvaluationNodeError,
        match="duplicate contradiction references",
    ):
        evaluate_dimensions_node(
            state,
            dimensions=(
                _dimension(
                    DimensionName.SEMANTIC_FIT,
                    "80",
                ),
            ),
            contradiction_refs=("evidence-1", "evidence-1"),
        )


def test_evaluate_dimensions_node_does_not_calculate_score() -> None:
    state = _state()

    result = evaluate_dimensions_node(
        state,
        dimensions=(
            _dimension(
                DimensionName.SEMANTIC_FIT,
                "80",
            ),
        ),
    )

    assert result.evaluation is not None
    assert result.score is None


def test_evaluate_dimensions_node_preserves_existing_score() -> None:
    state = _state()

    # The node is not allowed to mutate or recalculate score.
    result = evaluate_dimensions_node(
        state,
        dimensions=(
            _dimension(
                DimensionName.SEMANTIC_FIT,
                "80",
            ),
        ),
    )

    assert result.score is state.score


def test_evaluate_dimensions_node_preserves_existing_policy() -> None:
    state = _state()

    result = evaluate_dimensions_node(
        state,
        dimensions=(
            _dimension(
                DimensionName.SEMANTIC_FIT,
                "80",
            ),
        ),
    )

    assert result.policy is state.policy
