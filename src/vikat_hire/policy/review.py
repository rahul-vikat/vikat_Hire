from __future__ import annotations

from vikat_hire.contracts.common import ReviewReason
from vikat_hire.contracts.evaluation import ScopeAlignmentAssessment
from vikat_hire.contracts.policy import ReviewRequest
from vikat_hire.contracts.scope import JDScopeEvaluation


def build_scope_review_requests(*, jd_scope_evaluation: JDScopeEvaluation, scope_alignment: ScopeAlignmentAssessment) -> tuple[ReviewRequest, ...]:
    """Convert deterministic scope-policy signals into explicit review requests."""
    requests: list[ReviewRequest] = []
    if jd_scope_evaluation.review_required:
        requests.append(ReviewRequest(reason=ReviewReason.CONTRADICTION, blocking=True, evidence_refs=jd_scope_evaluation.evidence_refs, contradiction_refs=jd_scope_evaluation.contradiction_evidence_refs, requested_action="Review the contradictory JD scope evidence and resolve the required scope level before continuing seniority policy evaluation."))
    return tuple(requests)
