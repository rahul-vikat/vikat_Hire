from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import ContractModel, WorkflowStatus, new_id, utc_now
from .evaluation import EvaluationResult, ScopeAlignmentAssessment
from .evidence import Claim, ClaimReconciliation, Evidence, Provenance
from .explanation import ExplanationResult
from .inputs import ScreeningInput
from .matching import KeywordMatch, LLMSemanticProposal, SemanticMatch
from .policy import PolicyResult, ReviewRequest
from .scope import JDScopeEvaluation
from .scoring import ScoreResult


class ClassificationResult(ContractModel):
    jd_type: str

    rationale: str

    provenance_refs: tuple[str, ...]

    created_at: datetime = Field(default_factory=utc_now)


class ScreeningState(ContractModel):
    """
    Persistent state of one screening execution.

    This is a domain contract, not the LangGraph-specific implementation.
    The graph adapter will map this immutable model to its checkpoint state.
    """

    screening_id: str = Field(default_factory=new_id)

    status: WorkflowStatus = WorkflowStatus.CREATED

    current_node: str = "start"

    screening_input: ScreeningInput

    classification: ClassificationResult | None = None

    claims: tuple[Claim, ...] = ()
    provenances: tuple[Provenance, ...] = ()
    evidence: tuple[Evidence, ...] = ()

    keyword_matches: tuple[KeywordMatch, ...] = ()
    deterministic_semantic_matches: tuple[SemanticMatch, ...] = ()

    llm_semantic_proposals: tuple[LLMSemanticProposal, ...] = ()

    reconciliations: tuple[ClaimReconciliation, ...] = ()

    scope_alignment: ScopeAlignmentAssessment | None = None
    jd_scope_evaluation: JDScopeEvaluation | None = None

    evaluation: EvaluationResult | None = None

    score: ScoreResult | None = None

    policy: PolicyResult | None = None
    
    explanation: ExplanationResult | None = None

    pending_reviews: tuple[ReviewRequest, ...] = ()

    required_inputs_missing: tuple[str, ...] = ()

    errors: tuple[str, ...] = ()

    revision: int = 0

    updated_at: datetime = Field(default_factory=utc_now)
