from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    RequirementCategory,
    RequirementImportance,
    ReviewReason,
    SourceType,
    WorkflowStatus,
)
from vikat_hire.contracts.evaluation import DimensionEvaluation, EvaluationResult
from vikat_hire.contracts.normalization import (
    JDRequirement,
    NormalizationResult,
    NormalizedEducationRecord,
)
from vikat_hire.contracts.policy import GateResult, GateStatus, ReviewRequest
from vikat_hire.contracts.scoring import DimensionScore, ScoreResult
from vikat_hire.policy.evaluator import (
    MANDATORY_GATES,
    build_policy_result,
)
from vikat_hire.policy.gates import evaluate_mandatory_gates

REF = "policy-test-configuration@1.0.0"
SID = "screening-policy-test"


def _requirement(category: RequirementCategory, *, requirement_id: str = "req-1"):
    return JDRequirement(
        requirement_id=requirement_id,
        category=category,
        importance=RequirementImportance.MUST_HAVE,
        text=f"Required {category.value}",
        source_type=SourceType.JD_FILE,
        source_ref="jd-block-1",
        evidence_refs=(f"jd-evidence-{requirement_id}",),
        provenance_refs=("jd-provenance",),
    )


def _normalization(*requirements, education=()):
    return NormalizationResult(
        screening_id=SID,
        jd_requirements=tuple(requirements),
        education_records=tuple(education),
    )


def _education(education_id="education-1", evidence_ref="education-evidence-1"):
    return NormalizedEducationRecord(
        education_id=education_id,
        school_name="Example University",
        degree="BSc",
        field_of_study="Computer Science",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-profile",
        evidence_refs=(evidence_ref,),
        provenance_refs=(f"{education_id}-provenance",),
    )


def evaluation(excluded=False):
    return EvaluationResult(
        screening_id=SID,
        dimensions=(
            DimensionEvaluation(
                dimension=DimensionName.MUST_HAVE_COVERAGE,
                applicability=ApplicabilityStatus.NOT_APPLICABLE
                if excluded
                else ApplicabilityStatus.APPLICABLE,
                resolution=DimensionResolution.EXCLUDED
                if excluded
                else DimensionResolution.EVALUATED,
                raw_value=None if excluded else Decimal("80"),
                exclusion_reason=ExclusionReason.NOT_APPLICABLE if excluded else None,
                rationale="Dimension excluded." if excluded else "Dimension evaluated.",
            ),
        ),
        deterministic=True,
    )


def score():
    return ScoreResult(
        screening_id=SID,
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


def request():
    return ReviewRequest(
        reason=ReviewReason.CONTRADICTION,
        blocking=True,
        evidence_refs=("evidence-1",),
        contradiction_refs=("contradiction-1",),
        requested_action="Resolve the contradiction.",
    )


def _policy_gates(status=GateStatus.PASS):
    return tuple(
        GateResult(
            name=name,
            status=status,
            rationale="Test gate.",
            configuration_ref=REF,
        )
        for name in MANDATORY_GATES
    )


def policy(*, gates=None, ev=None, sc=None, reviews=()):
    return build_policy_result(
        screening_id=SID,
        gates=_policy_gates() if gates is None else gates,
        evaluation=ev,
        score=sc,
        review_requests=reviews,
        configuration_ref=REF,
    )


def test_no_requirements_are_not_applicable_and_complete_existing_policy():
    gates = evaluate_mandatory_gates(normalization=_normalization(), configuration_ref=REF)
    assert tuple(gate.status for gate in gates) == (GateStatus.NOT_APPLICABLE,) * 4
    result = policy(gates=gates, ev=evaluation(), sc=score())
    assert result.workflow_status is WorkflowStatus.COMPLETED
    assert result.suitability_eligible


@pytest.mark.parametrize(
    ("category", "gate_name"),
    [
        (RequirementCategory.CERTIFICATION, "certification"),
        (RequirementCategory.EDUCATION, "education"),
        (RequirementCategory.LOCATION, "location"),
        (RequirementCategory.AVAILABILITY, "availability"),
    ],
)
def test_applicable_requirement_fails_until_approved_matching_rule(category, gate_name):
    gates = evaluate_mandatory_gates(
        normalization=_normalization(_requirement(category)),
        configuration_ref=REF,
    )
    selected = next(gate for gate in gates if gate.name == gate_name)
    assert selected.status is GateStatus.FAIL
    assert selected.requirement_refs == ("req-1",)
    assert selected.evidence_refs == ()
    assert policy(gates=gates).workflow_status is WorkflowStatus.FAILED


def test_education_evidence_refs_are_preserved_but_do_not_imply_pass():
    gates = evaluate_mandatory_gates(
        normalization=_normalization(
            _requirement(RequirementCategory.EDUCATION),
            education=(_education(),),
        ),
        configuration_ref=REF,
    )
    education = next(gate for gate in gates if gate.name == "education")
    assert education.status is GateStatus.FAIL
    assert education.evidence_refs == ("education-evidence-1",)
    assert "rule is not approved" in education.rationale


def test_different_candidate_evidence_is_traced_independently():
    requirement = _requirement(RequirementCategory.EDUCATION)
    first = evaluate_mandatory_gates(
        normalization=_normalization(requirement, education=(_education("edu-a", "evidence-a"),)),
        configuration_ref=REF,
    )
    second = evaluate_mandatory_gates(
        normalization=_normalization(requirement, education=(_education("edu-b", "evidence-b"),)),
        configuration_ref=REF,
    )
    first_gate = next(gate for gate in first if gate.name == "education")
    second_gate = next(gate for gate in second if gate.name == "education")
    assert first_gate.status is second_gate.status is GateStatus.FAIL
    assert first_gate.evidence_refs == ("evidence-a",)
    assert second_gate.evidence_refs == ("evidence-b",)


def test_policy_status_preserves_fail_review_and_success_precedence():
    assert (
        policy(ev=evaluation(), sc=score(), reviews=(request(),)).workflow_status
        is WorkflowStatus.REVIEW_REQUIRED
    )
    passing_with_review = policy(
        gates=_policy_gates(), ev=evaluation(), sc=score(), reviews=(request(),)
    )
    assert passing_with_review.workflow_status is WorkflowStatus.REVIEW_REQUIRED
    failed_with_review = list(_policy_gates())
    failed_with_review[0] = failed_with_review[0].model_copy(update={"status": GateStatus.FAIL})
    result = policy(gates=tuple(failed_with_review), reviews=(request(),))
    assert result.workflow_status is WorkflowStatus.FAILED
    assert result.confidence_level == "low"


def test_gate_failure_does_not_create_review_request():
    gates = evaluate_mandatory_gates(
        normalization=_normalization(_requirement(RequirementCategory.CERTIFICATION)),
        configuration_ref=REF,
    )
    result = policy(gates=gates)
    assert result.workflow_status is WorkflowStatus.FAILED
    assert result.review_requests == ()


def test_invalid_gate_sets_raise():
    gates = _policy_gates()
    with pytest.raises(ValueError, match="exactly the four mandatory gates"):
        build_policy_result(
            screening_id=SID,
            gates=gates[:-1],
            evaluation=None,
            score=None,
            review_requests=(),
            configuration_ref=REF,
        )
    with pytest.raises(ValueError, match="each mandatory gate exactly once"):
        build_policy_result(
            screening_id=SID,
            gates=gates + (gates[0],),
            evaluation=None,
            score=None,
            review_requests=(),
            configuration_ref=REF,
        )


def test_policy_preserves_inputs_and_does_not_recalculate_score():
    ev, sc = evaluation(), score()
    before = ev.model_dump(), sc.model_dump()
    result = policy(ev=ev, sc=sc)
    assert result.workflow_status is WorkflowStatus.COMPLETED
    assert (ev.model_dump(), sc.model_dump()) == before
    assert sc.score == Decimal("80") and sc.applicable_weight_total == Decimal("30")
