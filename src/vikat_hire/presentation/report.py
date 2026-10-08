from __future__ import annotations

from vikat_hire.contracts.common import ContractModel, WorkflowStatus
from vikat_hire.contracts.evaluation import EvaluationResult
from vikat_hire.contracts.evidence import Claim, Evidence, Provenance
from vikat_hire.contracts.explanation import ExplanationResult
from vikat_hire.contracts.matching import KeywordMatch, LLMSemanticProposal, SemanticMatch
from vikat_hire.contracts.policy import PolicyResult, ReviewRequest
from vikat_hire.contracts.scoring import ScoreResult
from vikat_hire.contracts.state import ClassificationResult, ScreeningState


class ScreeningReportError(ValueError):
    """Raised when report input contains inconsistent authoritative artifacts."""


class ScreeningReport(ContractModel):
    """Read-only presentation of authoritative screening artifacts.

    Nested evaluations, score audits, policy outcomes, and explanations are
    passed through from ScreeningState. This model performs no decision logic.
    """

    screening_id: str
    workflow_status: WorkflowStatus
    classification: ClassificationResult | None = None
    claims: tuple[Claim, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    provenances: tuple[Provenance, ...] = ()
    keyword_matches: tuple[KeywordMatch, ...] = ()
    deterministic_semantic_matches: tuple[SemanticMatch, ...] = ()
    llm_semantic_proposals: tuple[LLMSemanticProposal, ...] = ()
    evaluation: EvaluationResult | None = None
    score: ScoreResult | None = None
    policy: PolicyResult | None = None
    review_requests: tuple[ReviewRequest, ...] = ()
    explanation: ExplanationResult | None = None


def build_screening_report(state: ScreeningState) -> ScreeningReport:
    """Project an immutable report from state without recalculating results."""
    if not isinstance(state, ScreeningState):
        raise ScreeningReportError("state must be a ScreeningState")

    artifacts = (
        ("evaluation", state.evaluation),
        ("score", state.score),
        ("policy", state.policy),
        ("explanation", state.explanation),
    )
    for name, artifact in artifacts:
        if artifact is not None and artifact.screening_id != state.screening_id:
            raise ScreeningReportError(
                f"{name} screening_id does not match state screening_id"
            )

    status = (
        state.policy.workflow_status
        if state.policy is not None
        else state.status
    )
    return ScreeningReport(
        screening_id=state.screening_id,
        workflow_status=status,
        classification=state.classification,
        claims=state.claims,
        evidence=state.evidence,
        provenances=state.provenances,
        keyword_matches=state.keyword_matches,
        deterministic_semantic_matches=state.deterministic_semantic_matches,
        llm_semantic_proposals=state.llm_semantic_proposals,
        evaluation=state.evaluation,
        score=state.score,
        policy=state.policy,
        review_requests=state.pending_reviews,
        explanation=state.explanation,
    )
