from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    RequirementCategory,
    RequirementImportance,
    ReviewReason,
    SourceType,
    WorkflowStatus,
)
from vikat_hire.contracts.evaluation import DimensionEvaluation, EvaluationResult
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.matching import LLMSemanticProposal
from vikat_hire.contracts.normalization import (
    JDRequirement,
    NormalizationResult,
    NormalizedEducationRecord,
)
from vikat_hire.contracts.policy import GateStatus, ReviewRequest
from vikat_hire.contracts.scoring import DimensionScore, ScoreResult
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.nodes.evaluate_policy import (
    PolicyEvaluationNodeError,
    evaluate_policy_node,
)

CONFIGURATION_REF = "policy-test-configuration@1.0.0"


def _state() -> ScreeningState:
    screening_input = ScreeningInput(
        jd=DocumentInput(
            kind="jd",
            filename="jd.txt",
            media_type="text/plain",
            content_hash="jd-hash",
            storage_ref="test://jd",
        ),
        resume=DocumentInput(
            kind="resume",
            filename="resume.txt",
            media_type="text/plain",
            content_hash="resume-hash",
            storage_ref="test://resume",
        ),
    )
    return ScreeningState(
        screening_id=screening_input.screening_id, screening_input=screening_input
    )


def _normalization(state, *categories, education=()):
    requirements = tuple(
        JDRequirement(
            requirement_id=f"req-{category.value}",
            category=category,
            importance=RequirementImportance.MUST_HAVE,
            text=f"Required {category.value}",
            source_type=SourceType.JD_FILE,
            source_ref="jd-block",
            evidence_refs=(f"jd-ref-{category.value}",),
            provenance_refs=("jd-provenance",),
        )
        for category in categories
    )
    return NormalizationResult(
        screening_id=state.screening_id,
        jd_requirements=requirements,
        education_records=tuple(education),
    )


def _education():
    return NormalizedEducationRecord(
        education_id="education-1",
        school_name="Example University",
        degree="BSc",
        field_of_study="Computer Science",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-profile",
        evidence_refs=("education-evidence-1",),
        provenance_refs=("education-provenance-1",),
    )


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


def test_evaluate_policy_node_attaches_candidate_specific_policy():
    state = _state()
    state = state.model_copy(
        update={"evaluation": _evaluation(state.screening_id), "score": _score(state.screening_id)}
    )
    normalization = _normalization(state)
    result = evaluate_policy_node(
        state, normalization=normalization, configuration_ref=CONFIGURATION_REF
    )
    assert result.policy is not None
    assert result.policy.workflow_status is WorkflowStatus.COMPLETED
    assert result.policy.suitability_eligible is True
    assert tuple(gate.status for gate in result.policy.gates) == (GateStatus.NOT_APPLICABLE,) * 4


def test_applicable_education_fails_even_when_record_exists_until_rule_is_approved():
    state = _state()
    normalization = _normalization(state, RequirementCategory.EDUCATION, education=(_education(),))
    result = evaluate_policy_node(
        state, normalization=normalization, configuration_ref=CONFIGURATION_REF
    )
    education = next(gate for gate in result.policy.gates if gate.name == "education")
    assert education.status is GateStatus.FAIL
    assert education.requirement_refs == ("req-education",)
    assert education.evidence_refs == ("education-evidence-1",)
    assert result.policy.review_requests == ()
    assert result.policy.workflow_status is WorkflowStatus.FAILED


def test_gate_failure_does_not_create_review_and_independent_reviews_remain():
    state = _state()
    normalization = _normalization(state, RequirementCategory.CERTIFICATION)
    independent_review = _review_request()
    result = evaluate_policy_node(
        state,
        normalization=normalization,
        configuration_ref=CONFIGURATION_REF,
        review_requests=(independent_review,),
    )
    assert result.pending_reviews == (independent_review,)
    assert result.policy.review_requests == (independent_review,)
    assert result.policy.workflow_status is WorkflowStatus.FAILED


def test_policy_node_preserves_evaluation_and_score():
    state = _state()
    evaluation = _evaluation(state.screening_id)
    score = _score(state.screening_id)
    state = state.model_copy(update={"evaluation": evaluation, "score": score})
    result = evaluate_policy_node(
        state, normalization=_normalization(state), configuration_ref=CONFIGURATION_REF
    )
    assert result.evaluation == evaluation
    assert result.score == score


def test_policy_node_rejects_invalid_state_and_normalization_identity():
    state = _state()
    with pytest.raises(PolicyEvaluationNodeError, match="ScreeningState"):
        evaluate_policy_node(
            object(), normalization=_normalization(state), configuration_ref=CONFIGURATION_REF
        )
    mismatch = NormalizationResult(screening_id="other-screening")
    with pytest.raises(PolicyEvaluationNodeError, match="normalization screening_id"):
        evaluate_policy_node(state, normalization=mismatch, configuration_ref=CONFIGURATION_REF)


def test_policy_node_rejects_blank_configuration_and_mismatched_artifacts():
    state = _state()
    with pytest.raises(PolicyEvaluationNodeError, match="configuration_ref must not be blank"):
        evaluate_policy_node(state, normalization=_normalization(state), configuration_ref="  ")
    mismatched = state.model_copy(update={"evaluation": _evaluation("other")})
    with pytest.raises(PolicyEvaluationNodeError, match="evaluation screening_id"):
        evaluate_policy_node(
            mismatched, normalization=_normalization(state), configuration_ref=CONFIGURATION_REF
        )
    mismatched_score = state.model_copy(update={"score": _score("other")})
    with pytest.raises(PolicyEvaluationNodeError, match="score screening_id"):
        evaluate_policy_node(
            mismatched_score,
            normalization=_normalization(state),
            configuration_ref=CONFIGURATION_REF,
        )


def test_policy_node_does_not_recalculate_score():
    state = _state()
    score = _score(state.screening_id)
    state = state.model_copy(update={"evaluation": _evaluation(state.screening_id), "score": score})
    result = evaluate_policy_node(
        state, normalization=_normalization(state), configuration_ref=CONFIGURATION_REF
    )
    assert result.score.score == Decimal("80")
    assert result.score.applicable_weight_total == Decimal("30")


def test_llm_semantic_proposal_cannot_change_gate_or_policy_outcome():
    state = _state()
    normalization = _normalization(state, RequirementCategory.EDUCATION)
    proposal_values = (Decimal("0"), Decimal("100"))
    policies = []
    for proposal_score in proposal_values:
        proposal = LLMSemanticProposal(
            requirement_id="req-education",
            score=proposal_score,
            rationale="Advisory-only test proposal.",
            model_config_ref="test-model@1",
            provenance_refs=("model-provenance",),
        )
        candidate_state = state.model_copy(update={"llm_semantic_proposals": (proposal,)})
        result = evaluate_policy_node(
            candidate_state,
            normalization=normalization,
            configuration_ref=CONFIGURATION_REF,
        )
        policies.append(result.policy)

    assert tuple(gate.status for gate in policies[0].gates) == tuple(
        gate.status for gate in policies[1].gates
    )
    assert tuple(gate.rationale for gate in policies[0].gates) == tuple(
        gate.rationale for gate in policies[1].gates
    )
    assert policies[0].workflow_status is policies[1].workflow_status is WorkflowStatus.FAILED
