from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    ReviewReason,
    WorkflowStatus,
)
from vikat_hire.contracts.evaluation import (
    DimensionEvaluation,
    EvaluationResult,
)
from vikat_hire.contracts.inputs import (
    DocumentInput,
    ScreeningInput,
)
from vikat_hire.contracts.policy import ReviewRequest
from vikat_hire.contracts.scoring import (
    DimensionScore,
    ScoreResult,
)
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.contracts.common import InputKind
from vikat_hire.orchestration.nodes.evaluate_policy import (
    PolicyEvaluationNodeError,
    evaluate_policy_node,
)
from vikat_hire.policy.evaluator import MANDATORY_GATES


CONFIGURATION_REF = "policy-test-configuration@1.0.0"


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


def _state() -> ScreeningState:
    screening_input = _screening_input()

    return ScreeningState(
        screening_id=screening_input.screening_id,
        screening_input=screening_input,
    )


def _field_presence() -> dict[str, bool]:
    return {name: True for name in MANDATORY_GATES}


def _evaluation(screening_id: str) -> EvaluationResult:
    return EvaluationResult(
        screening_id=screening_id,
        dimensions=(
            DimensionEvaluation(
                dimension=DimensionName.MUST_HAVE_COVERAGE,
                applicability=ApplicabilityStatus.APPLICABLE,
                resolution=DimensionResolution.EVALUATED,
                raw_value=Decimal("80"),
                rationale="Deterministically evaluated.",
            ),
        ),
        deterministic=True,
    )


def _score(screening_id: str) -> ScoreResult:
    return ScoreResult(
        screening_id=screening_id,
        dimensions=(
            DimensionScore(
                dimension=DimensionName.MUST_HAVE_COVERAGE,
                resolution=DimensionResolution.EVALUATED,
                weight=Decimal("30"),
                raw_value=Decimal("80"),
                normalized_value=Decimal("0.80"),
                weighted_contribution=Decimal("24"),
            ),
        ),
        applicable_weight_total=Decimal("30"),
        score=Decimal("80"),
        audit=(),
    )


def _review_request() -> ReviewRequest:
    return ReviewRequest(
        reason=ReviewReason.CONTRADICTION,
        blocking=True,
        evidence_refs=("evidence-1",),
        contradiction_refs=("contradiction-1",),
        requested_action="Resolve the contradiction.",
    )


def test_evaluate_policy_node_attaches_policy_result() -> None:
    state = _state()

    state = state.model_copy(
        update={
            "evaluation": _evaluation(state.screening_id),
            "score": _score(state.screening_id),
        }
    )

    result = evaluate_policy_node(
        state,
        field_presence=_field_presence(),
        configuration_ref=CONFIGURATION_REF,
    )

    assert result.policy is not None
    assert result.policy.screening_id == state.screening_id
    assert result.policy.workflow_status is WorkflowStatus.COMPLETED
    assert result.policy.suitability_eligible is True
    assert result.policy.confidence_level == "high"

def test_evaluate_policy_node_preserves_evaluation_and_score() -> None:
    state = _state()
    evaluation = _evaluation(state.screening_id)
    score = _score(state.screening_id)

    state = state.model_copy(
        update={
            "evaluation": evaluation,
            "score": score,
        }
    )

    result = evaluate_policy_node(
        state,
        field_presence=_field_presence(),
        configuration_ref=CONFIGURATION_REF,
    )

    assert result.evaluation == evaluation
    assert result.score == score


def test_evaluate_policy_node_failed_gate_blocks_eligibility() -> None:
    state = _state()

    fields = _field_presence()
    fields["education"] = False

    result = evaluate_policy_node(
        state,
        field_presence=fields,
        configuration_ref=CONFIGURATION_REF,
    )

    assert result.policy is not None
    assert result.policy.workflow_status is WorkflowStatus.FAILED
    assert result.policy.suitability_eligible is False


def test_evaluate_policy_node_preserves_review_requests() -> None:
    state = _state()
    request = _review_request()

    result = evaluate_policy_node(
        state,
        field_presence=_field_presence(),
        configuration_ref=CONFIGURATION_REF,
        review_requests=(request,),
    )

    assert result.pending_reviews == (request,)
    assert result.policy is not None
    assert result.policy.review_requests == (request,)
    assert result.policy.workflow_status is WorkflowStatus.REVIEW_REQUIRED
    assert result.policy.suitability_eligible is True
    assert result.policy.confidence_level == "low"


def test_evaluate_policy_node_rejects_blank_configuration_ref() -> None:
    with pytest.raises(
        PolicyEvaluationNodeError,
        match="configuration_ref must not be blank",
    ):
        evaluate_policy_node(
            _state(),
            field_presence=_field_presence(),
            configuration_ref="   ",
        )


def test_evaluate_policy_node_rejects_mismatched_evaluation() -> None:
    state = _state()

    evaluation = _evaluation("different-screening-id")

    state = state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )

    with pytest.raises(
        PolicyEvaluationNodeError,
        match="evaluation screening_id does not match",
    ):
        evaluate_policy_node(
            state,
            field_presence=_field_presence(),
            configuration_ref=CONFIGURATION_REF,
        )


def test_evaluate_policy_node_rejects_mismatched_score() -> None:
    state = _state()

    score = _score("different-screening-id")

    state = state.model_copy(
        update={
            "score": score,
        }
    )

    with pytest.raises(
        PolicyEvaluationNodeError,
        match="score screening_id does not match",
    ):
        evaluate_policy_node(
            state,
            field_presence=_field_presence(),
            configuration_ref=CONFIGURATION_REF,
        )


def test_evaluate_policy_node_rejects_unsupported_policy_field() -> None:
    fields = _field_presence()
    fields["unsupported"] = True

    with pytest.raises(
        ValueError,
        match="unsupported policy fields",
    ):
        evaluate_policy_node(
            _state(),
            field_presence=fields,
            configuration_ref=CONFIGURATION_REF,
        )


def test_evaluate_policy_node_does_not_recalculate_score() -> None:
    state = _state()
    evaluation = _evaluation(state.screening_id)
    score = _score(state.screening_id)

    state = state.model_copy(
        update={
            "evaluation": evaluation,
            "score": score,
        }
    )

    result = evaluate_policy_node(
        state,
        field_presence=_field_presence(),
        configuration_ref=CONFIGURATION_REF,
    )

    assert result.score is not None
    assert result.score.score == Decimal("80")
    assert result.score.applicable_weight_total == Decimal("30")