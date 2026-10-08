from __future__ import annotations

from vikat_hire.contracts.common import DimensionResolution, EvidenceConfidence, WorkflowStatus
from vikat_hire.contracts.evaluation import EvaluationResult
from vikat_hire.contracts.policy import GateResult, GateStatus, PolicyResult, ReviewRequest
from vikat_hire.contracts.scoring import ScoreResult
from vikat_hire.policy.gates import MANDATORY_GATES


def _has_material_review(*, review_requests: tuple[ReviewRequest, ...]) -> bool:
    return any(request.blocking for request in review_requests)


def _confidence_level(
    *,
    review_requests: tuple[ReviewRequest, ...],
    evaluation: EvaluationResult | None,
    score: ScoreResult | None,
) -> str:
    if _has_material_review(review_requests=review_requests):
        return EvidenceConfidence.LOW.value
    if evaluation is None or score is None or not evaluation.dimensions:
        return EvidenceConfidence.MEDIUM.value
    if any(
        dimension.resolution is DimensionResolution.EXCLUDED for dimension in evaluation.dimensions
    ):
        return EvidenceConfidence.MEDIUM.value
    return EvidenceConfidence.HIGH.value


def build_policy_result(
    *,
    screening_id: str,
    gates: tuple[GateResult, ...],
    evaluation: EvaluationResult | None,
    score: ScoreResult | None,
    review_requests: tuple[ReviewRequest, ...],
    configuration_ref: str,
) -> PolicyResult:
    expected = set(MANDATORY_GATES)
    actual = {gate.name for gate in gates}
    if actual != expected:
        missing = expected - actual
        unexpected = actual - expected
        parts = []
        if missing:
            parts.append("missing=" + ",".join(sorted(missing)))
        if unexpected:
            parts.append("unexpected=" + ",".join(sorted(unexpected)))
        raise ValueError(
            "policy gates must contain exactly the four mandatory gates: " + "; ".join(parts)
        )
    if len(gates) != len(MANDATORY_GATES):
        raise ValueError("policy gates must contain each mandatory gate exactly once")
    failed = any(gate.status is GateStatus.FAIL for gate in gates)
    if failed:
        status, eligible = WorkflowStatus.FAILED, False
    elif review_requests:
        status, eligible = WorkflowStatus.REVIEW_REQUIRED, True
    else:
        status, eligible = WorkflowStatus.COMPLETED, True
    return PolicyResult(
        screening_id=screening_id,
        gates=gates,
        review_requests=review_requests,
        workflow_status=status,
        suitability_eligible=eligible,
        confidence_level=_confidence_level(
            review_requests=review_requests, evaluation=evaluation, score=score
        ),
        configuration_ref=configuration_ref,
    )
