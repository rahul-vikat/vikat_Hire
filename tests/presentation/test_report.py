from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    DimensionName,
    DimensionResolution,
    WorkflowStatus,
)
from vikat_hire.contracts.evaluation import DimensionEvaluation, EvaluationResult
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.policy import PolicyResult
from vikat_hire.contracts.scoring import DimensionScore, ScoreAudit, ScoreResult
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.presentation.report import (
    ScreeningReportError,
    build_screening_report,
)


def _state() -> ScreeningState:
    screening_id = "report-screening-1"
    screening_input = ScreeningInput(
        screening_id=screening_id,
        jd=DocumentInput(
            kind="jd",
            filename="jd.txt",
            media_type="text/plain",
            content_hash="jd-hash",
            storage_ref="opaque-jd",
        ),
        resume=DocumentInput(
            kind="resume",
            filename="resume.txt",
            media_type="text/plain",
            content_hash="resume-hash",
            storage_ref="opaque-resume",
        ),
    )
    return ScreeningState(
        screening_id=screening_id,
        screening_input=screening_input,
    )


def test_report_projects_unfinished_state_without_inventing_results() -> None:
    state = _state()

    report = build_screening_report(state)

    assert report.screening_id == state.screening_id
    assert report.workflow_status is WorkflowStatus.CREATED
    assert report.evaluation is None
    assert report.score is None
    assert report.policy is None
    assert report.explanation is None


def test_report_preserves_authoritative_evaluation_score_and_policy() -> None:
    state = _state()
    evaluation = EvaluationResult(
        screening_id=state.screening_id,
        dimensions=(
            DimensionEvaluation(
                dimension=DimensionName.MUST_HAVE_COVERAGE,
                applicability="applicable",
                resolution=DimensionResolution.EVALUATED,
                raw_value=Decimal("80"),
                evidence_refs=("evidence-1",),
                requirement_refs=("requirement-1",),
                provenance_refs=("provenance-1",),
                rationale="Deterministic result.",
            ),
        ),
    )
    score = ScoreResult(
        screening_id=state.screening_id,
        dimensions=(
            DimensionScore(
                dimension=DimensionName.MUST_HAVE_COVERAGE,
                resolution=DimensionResolution.EVALUATED,
                weight=Decimal("30"),
                raw_value=Decimal("80"),
                normalized_value=Decimal("0.8"),
                weighted_contribution=Decimal("24"),
                evidence_refs=("evidence-1",),
            ),
        ),
        applicable_weight_total=Decimal("30"),
        score=Decimal("80"),
        audit=(
            ScoreAudit(
                dimension=DimensionName.MUST_HAVE_COVERAGE,
                input_evaluation_ref=evaluation.dimensions[0].dimension_id,
                evidence_refs=("evidence-1",),
                configuration_ref="verifyhire-scoring@2.2.0",
                weight=Decimal("30"),
                normalized_value=Decimal("0.8"),
                weighted_contribution=Decimal("24"),
            ),
        ),
    )
    policy = PolicyResult(
        screening_id=state.screening_id,
        gates=(),
        review_requests=(),
        workflow_status=WorkflowStatus.COMPLETED,
        suitability_eligible=True,
        confidence_level="high",
        configuration_ref="policy@1",
    )
    state = state.model_copy(
        update={"evaluation": evaluation, "score": score, "policy": policy}
    )

    report = build_screening_report(state)

    assert report.evaluation is evaluation
    assert report.score is score
    assert report.policy is policy
    assert report.workflow_status is WorkflowStatus.COMPLETED
    assert report.score.score == Decimal("80")
    assert report.score.audit[0].input_evaluation_ref == (
        evaluation.dimensions[0].dimension_id
    )


def test_report_rejects_cross_screening_authoritative_artifact() -> None:
    state = _state()
    mismatched = EvaluationResult(screening_id="another-screening", dimensions=())
    state = state.model_copy(update={"evaluation": mismatched})

    with pytest.raises(ScreeningReportError, match="evaluation screening_id"):
        build_screening_report(state)


def test_report_rejects_non_screening_state() -> None:
    with pytest.raises(ScreeningReportError, match="ScreeningState"):
        build_screening_report(object())  # type: ignore[arg-type]
