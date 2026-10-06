from decimal import Decimal

import pytest

from vikat_hire.contracts.common import ApplicabilityStatus, DimensionName, DimensionResolution, ExclusionReason, ReviewReason, WorkflowStatus
from vikat_hire.contracts.evaluation import DimensionEvaluation, EvaluationResult
from vikat_hire.contracts.policy import GateResult, ReviewRequest
from vikat_hire.contracts.scoring import DimensionScore, ScoreResult
from vikat_hire.policy.evaluator import GATE_AVAILABILITY, GATE_CERTIFICATION, GATE_EDUCATION, GATE_LOCATION, MANDATORY_GATES, build_mandatory_gates, build_policy_result

REF = "policy-test-configuration@1.0.0"
SID = "screening-policy-test"


def fields():
    return {name: True for name in MANDATORY_GATES}


def evaluation(excluded=False):
    return EvaluationResult(screening_id=SID, dimensions=(DimensionEvaluation(dimension=DimensionName.MUST_HAVE_COVERAGE, applicability=ApplicabilityStatus.NOT_APPLICABLE if excluded else ApplicabilityStatus.APPLICABLE, resolution=DimensionResolution.EXCLUDED if excluded else DimensionResolution.EVALUATED, raw_value=None if excluded else Decimal("80"), exclusion_reason=ExclusionReason.NOT_APPLICABLE if excluded else None, rationale="Dimension excluded." if excluded else "Dimension evaluated."),), deterministic=True)


def score():
    return ScoreResult(screening_id=SID, dimensions=(DimensionScore(dimension=DimensionName.MUST_HAVE_COVERAGE, resolution=DimensionResolution.EVALUATED, weight=Decimal("30"), raw_value=Decimal("80"), normalized_value=Decimal("0.80"), weighted_contribution=Decimal("24")),), applicable_weight_total=Decimal("30"), score=Decimal("80"), audit=())


def request():
    return ReviewRequest(reason=ReviewReason.CONTRADICTION, blocking=True, evidence_refs=("evidence-1",), contradiction_refs=("contradiction-1",), requested_action="Resolve the contradiction.")


def policy(*, presence=None, ev=None, sc=None, reviews=()):
    gates = build_mandatory_gates(field_presence=fields() if presence is None else presence, configuration_ref=REF)
    return build_policy_result(screening_id=SID, gates=gates, evaluation=ev, score=sc, review_requests=reviews, configuration_ref=REF)


def test_all_gates_completed_high_confidence():
    result = policy(ev=evaluation(), sc=score())
    assert result.workflow_status is WorkflowStatus.COMPLETED
    assert result.suitability_eligible and result.confidence_level == "high"


@pytest.mark.parametrize("missing", MANDATORY_GATES)
def test_missing_gate_fails(missing):
    present = fields(); present[missing] = False
    result = policy(presence=present, ev=evaluation(), sc=score())
    assert result.workflow_status is WorkflowStatus.FAILED
    assert result.suitability_eligible is False
    assert tuple(g.name for g in result.gates if not g.passed) == (missing,)


def test_review_requires_review_and_failed_gate_wins():
    assert policy(ev=evaluation(), sc=score(), reviews=(request(),)).workflow_status is WorkflowStatus.REVIEW_REQUIRED
    present = fields(); present[GATE_EDUCATION] = False
    result = policy(presence=present, ev=evaluation(), sc=score(), reviews=(request(),))
    assert result.workflow_status is WorkflowStatus.FAILED
    assert result.confidence_level == "low"


def test_conservative_confidence_cases():
    assert policy().confidence_level == "medium"
    assert policy(ev=evaluation(), sc=None).confidence_level == "medium"
    assert policy(ev=evaluation(excluded=True), sc=score()).confidence_level == "medium"


def test_unsupported_field_raises():
    present = fields(); present["unsupported"] = True
    with pytest.raises(ValueError, match="unsupported policy fields"):
        build_mandatory_gates(field_presence=present, configuration_ref=REF)


def test_invalid_gate_sets_raise():
    gates = build_mandatory_gates(field_presence=fields(), configuration_ref=REF)
    with pytest.raises(ValueError, match="exactly the four mandatory gates"):
        build_policy_result(screening_id=SID, gates=gates[:-1], evaluation=None, score=None, review_requests=(), configuration_ref=REF)
    with pytest.raises(ValueError, match="each mandatory gate exactly once"):
        build_policy_result(screening_id=SID, gates=gates + (gates[0],), evaluation=None, score=None, review_requests=(), configuration_ref=REF)
    unexpected = gates[:3] + (GateResult(name="unexpected", passed=True, requirement_refs=("unexpected",), rationale="Unexpected gate.", configuration_ref=REF),)
    with pytest.raises(ValueError, match="exactly the four mandatory gates"):
        build_policy_result(screening_id=SID, gates=unexpected, evaluation=None, score=None, review_requests=(), configuration_ref=REF)


def test_policy_preserves_inputs_and_does_not_recalculate_score():
    ev, sc = evaluation(), score()
    before = ev.model_dump(), sc.model_dump()
    result = policy(ev=ev, sc=sc)
    assert result.workflow_status is WorkflowStatus.COMPLETED
    assert (ev.model_dump(), sc.model_dump()) == before
    assert sc.score == Decimal("80") and sc.applicable_weight_total == Decimal("30")
