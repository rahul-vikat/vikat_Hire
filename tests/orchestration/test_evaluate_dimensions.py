from __future__ import annotations

from decimal import Decimal
from importlib import import_module

import pytest

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    InputKind,
    ScopeLevel,
)
from vikat_hire.contracts.evaluation import (
    DimensionEvaluation,
    ScopeAlignmentAssessment,
    SeniorityScopeEvaluation,
)
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.dimensions import DimensionEvaluationError
from vikat_hire.orchestration.nodes.evaluate_dimensions import (
    DimensionEvaluationNodeError,
    evaluate_dimensions_node,
)

NODE_MODULE = import_module(
    "vikat_hire.orchestration.nodes.evaluate_dimensions"
)


def _state(
    *,
    scope_alignment: ScopeAlignmentAssessment | None = None,
) -> ScreeningState:
    return ScreeningState(
        screening_id="screening-1",
        screening_input=ScreeningInput(
            screening_id="screening-1",
            jd=DocumentInput(
                input_id="jd-1",
                kind=InputKind.JD,
                filename="jd.txt",
                media_type="text/plain",
                content_hash="jd-hash",
                storage_ref="jd-ref",
            ),
            resume=DocumentInput(
                input_id="resume-1",
                kind=InputKind.RESUME,
                filename="resume.txt",
                media_type="text/plain",
                content_hash="resume-hash",
                storage_ref="resume-ref",
            ),
        ),
        scope_alignment=scope_alignment,
    )


def _seniority(
    *,
    resolution: DimensionResolution = DimensionResolution.EVALUATED,
) -> SeniorityScopeEvaluation:
    evaluated = resolution is DimensionResolution.EVALUATED
    return SeniorityScopeEvaluation(
        candidate_level=ScopeLevel.L2,
        required_level=ScopeLevel.L3,
        resolution=resolution,
        delta=-1 if evaluated else None,
        raw_value=Decimal("75") if evaluated else None,
        exclusion_reason=None if evaluated else ExclusionReason.INSUFFICIENT_EVIDENCE,
        evidence_refs=("candidate-scope-evidence",),
        provenance_refs=("candidate-provenance", "jd-provenance"),
        rationale="Deterministic scope alignment.",
    )


def _scope_alignment(
    *,
    resolution: DimensionResolution = DimensionResolution.EVALUATED,
) -> ScopeAlignmentAssessment:
    return ScopeAlignmentAssessment(
        seniority_evaluation=_seniority(resolution=resolution),
    )


def _dimension(
    dimension: DimensionName = DimensionName.SEMANTIC_FIT,
    raw_value: Decimal = Decimal("80"),
) -> DimensionEvaluation:
    return DimensionEvaluation(
        dimension=dimension,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=raw_value,
        evidence_refs=("existing-evidence",),
        provenance_refs=("existing-provenance",),
        rationale=f"Evaluation for {dimension.value}.",
    )


def test_state_scope_alignment_adds_exactly_one_seniority_dimension() -> None:
    result = evaluate_dimensions_node(
        _state(scope_alignment=_scope_alignment()),
        dimensions=(_dimension(),),
    )

    assert result.evaluation is not None
    seniority_dimensions = tuple(
        dimension
        for dimension in result.evaluation.dimensions
        if dimension.dimension is DimensionName.SENIORITY_SCOPE_ALIGNMENT
    )
    assert len(seniority_dimensions) == 1


def test_seniority_raw_value_evidence_and_provenance_are_preserved() -> None:
    result = evaluate_dimensions_node(
        _state(scope_alignment=_scope_alignment()),
        dimensions=(),
    )

    assert result.evaluation is not None
    dimension = result.evaluation.dimensions[0]
    assert dimension.dimension is DimensionName.SENIORITY_SCOPE_ALIGNMENT
    assert dimension.raw_value == Decimal("75")
    assert dimension.evidence_refs == ("candidate-scope-evidence",)
    assert dimension.provenance_refs == (
        "candidate-provenance",
        "jd-provenance",
    )


def test_excluded_seniority_remains_excluded_without_raw_value() -> None:
    result = evaluate_dimensions_node(
        _state(
            scope_alignment=_scope_alignment(
                resolution=DimensionResolution.EXCLUDED
            )
        ),
        dimensions=(),
    )

    assert result.evaluation is not None
    dimension = result.evaluation.dimensions[0]
    assert dimension.resolution is DimensionResolution.EXCLUDED
    assert dimension.raw_value is None
    assert dimension.exclusion_reason is ExclusionReason.INSUFFICIENT_EVIDENCE


def test_caller_supplied_seniority_is_rejected_when_state_has_alignment() -> None:
    with pytest.raises(
        DimensionEvaluationNodeError,
        match="must not include SENIORITY_SCOPE_ALIGNMENT",
    ):
        evaluate_dimensions_node(
            _state(scope_alignment=_scope_alignment()),
            dimensions=(_dimension(DimensionName.SENIORITY_SCOPE_ALIGNMENT),),
        )


def test_missing_scope_alignment_does_not_invent_seniority_dimension() -> None:
    result = evaluate_dimensions_node(
        _state(),
        dimensions=(_dimension(),),
    )

    assert result.evaluation is not None
    assert all(
        item.dimension is not DimensionName.SENIORITY_SCOPE_ALIGNMENT
        for item in result.evaluation.dimensions
    )


def test_existing_dimensions_and_contradiction_refs_are_preserved() -> None:
    dimensions = (
        _dimension(DimensionName.SEMANTIC_FIT),
        _dimension(DimensionName.MUST_HAVE_COVERAGE, Decimal("91")),
    )
    result = evaluate_dimensions_node(
        _state(scope_alignment=_scope_alignment()),
        dimensions=dimensions,
        contradiction_refs=("contradiction-1",),
    )

    assert result.evaluation is not None
    assert result.evaluation.contradiction_refs == ("contradiction-1",)
    values = {
        item.dimension: item.raw_value
        for item in result.evaluation.dimensions
    }
    assert values[DimensionName.SEMANTIC_FIT] == Decimal("80")
    assert values[DimensionName.MUST_HAVE_COVERAGE] == Decimal("91")
    assert values[DimensionName.SENIORITY_SCOPE_ALIGNMENT] == Decimal("75")


def test_invalid_state_and_dimension_items_fail() -> None:
    with pytest.raises(DimensionEvaluationNodeError, match="ScreeningState"):
        evaluate_dimensions_node(object(), dimensions=())  # type: ignore[arg-type]

    with pytest.raises(DimensionEvaluationNodeError, match="DimensionEvaluation"):
        evaluate_dimensions_node(_state(), dimensions=("invalid",))  # type: ignore[arg-type]

    with pytest.raises(DimensionEvaluationNodeError, match="iterable"):
        evaluate_dimensions_node(_state(), dimensions=None)  # type: ignore[arg-type]


def test_conversion_error_is_translated_and_chained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cause = DimensionEvaluationError("invalid seniority conversion")

    def fail(*, evaluation):
        raise cause

    monkeypatch.setattr(NODE_MODULE, "evaluate_seniority_dimension", fail)

    with pytest.raises(DimensionEvaluationNodeError) as error:
        evaluate_dimensions_node(
            _state(scope_alignment=_scope_alignment()),
            dimensions=(),
        )

    assert error.value.__cause__ is cause


def test_final_evaluation_is_deterministic() -> None:
    state = _state(scope_alignment=_scope_alignment())
    dimensions = (_dimension(),)

    first = evaluate_dimensions_node(state, dimensions=dimensions).evaluation
    second = evaluate_dimensions_node(state, dimensions=dimensions).evaluation

    assert first is not None
    assert second is not None
    exclude = {
        "created_at": True,
        "dimensions": {
            "__all__": {
                "created_at": True,
                "dimension_id": True,
            }
        },
    }
    assert first.model_dump(exclude=exclude) == second.model_dump(
        exclude=exclude
    )
