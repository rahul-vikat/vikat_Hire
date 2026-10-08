from __future__ import annotations

from decimal import Decimal
from importlib import import_module

import pytest

from vikat_hire.contracts.common import (
    AccessStatus,
    DerivationMethod,
    DimensionResolution,
    ExclusionReason,
    InputKind,
    SourceType,
)
from vikat_hire.contracts.evidence import Provenance
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.normalization import (
    NormalizationResult,
    NormalizedJDScopeEvidence,
    NormalizedScopeEvidence,
)
from vikat_hire.contracts.scope import (
    ScopeEvidence,
    ScopeEvidenceCategory,
    ScopeEvidencePolarity,
)
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.seniority import evaluate_scope_alignment
from vikat_hire.orchestration.nodes.evaluate_seniority import (
    SeniorityEvaluationNodeError,
    evaluate_seniority_node,
)

NODE_MODULE = import_module(
    "vikat_hire.orchestration.nodes.evaluate_seniority"
)


def _state(
    *,
    provenances: tuple[Provenance, ...] = (),
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
        provenances=provenances,
        updated_at="2026-10-08T00:00:00Z",
    )


def _provenance(provenance_id: str, source_type: SourceType) -> Provenance:
    return Provenance(
        provenance_id=provenance_id,
        source_type=source_type,
        source_ref=f"{source_type.value}-source",
        method=DerivationMethod.PARSER,
        access_status=AccessStatus.AUTHORIZED,
    )


def _candidate_scope(
    evidence_id: str,
    category: ScopeEvidenceCategory,
    provenance_ref: str = "candidate-provenance",
) -> NormalizedScopeEvidence:
    return NormalizedScopeEvidence(
        scope_evidence=ScopeEvidence(
            evidence_id=evidence_id,
            categories=(category,),
            explicit_text=f"Candidate evidence: {evidence_id}.",
            provenance_refs=(provenance_ref,),
        ),
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        evidence_refs=(f"source-evidence-{evidence_id}",),
        provenance_refs=(provenance_ref,),
    )


def _jd_scope(
    evidence_id: str,
    category: ScopeEvidenceCategory,
    *,
    polarity: ScopeEvidencePolarity = ScopeEvidencePolarity.SUPPORTING,
    provenance_ref: str = "jd-provenance",
) -> NormalizedJDScopeEvidence:
    return NormalizedJDScopeEvidence(
        evidence_id=evidence_id,
        categories=(category,),
        polarity=polarity,
        explicit_text=f"JD evidence: {evidence_id}.",
        provenance_refs=(provenance_ref,),
    )


def _normalization(
    *,
    candidate: tuple[NormalizedScopeEvidence, ...] | None = None,
    jd: tuple[NormalizedJDScopeEvidence, ...] | None = None,
    screening_id: str = "screening-1",
) -> NormalizationResult:
    if candidate is None:
        candidate = (
            _candidate_scope("candidate-ownership", ScopeEvidenceCategory.OWNERSHIP),
            _candidate_scope(
                "candidate-decisions",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        )
    if jd is None:
        jd = (
            _jd_scope("jd-ownership", ScopeEvidenceCategory.OWNERSHIP),
            _jd_scope(
                "jd-decisions",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
            _jd_scope(
                "jd-production",
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
        )
    return NormalizationResult(
        screening_id=screening_id,
        scope_evidence=candidate,
        jd_scope_evidence=jd,
    )


def _state_with_provenance() -> ScreeningState:
    return _state(
        provenances=(
            _provenance("candidate-provenance", SourceType.RESUME_FILE),
            _provenance("jd-provenance", SourceType.JD_FILE),
        )
    )


def test_evaluated_scope_alignment_is_stored_without_final_dimension() -> None:
    state = _state_with_provenance()
    normalization = _normalization()

    result = evaluate_seniority_node(state, normalization=normalization)

    assert result.scope_alignment is not None
    evaluation = result.scope_alignment.seniority_evaluation
    assert evaluation.resolution is DimensionResolution.EVALUATED
    assert evaluation.candidate_level.value == "L2"
    assert evaluation.required_level.value == "L3"
    assert evaluation.delta == -1
    assert evaluation.raw_value == Decimal("75")
    assert result.evaluation is None
    assert result.score is None


def test_node_passes_contract_evidence_and_provenance_to_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state_with_provenance()
    normalization = _normalization()
    actual = evaluate_scope_alignment(
        candidate_evidence=tuple(
            item.scope_evidence for item in normalization.scope_evidence
        ),
        jd_evidence=tuple(
            item.to_evaluation_evidence()
            for item in normalization.jd_scope_evidence
        ),
        provenance_refs=("candidate-provenance", "jd-provenance"),
    )
    received: dict[str, object] = {}

    def spy(**kwargs):
        received.update(kwargs)
        return actual

    monkeypatch.setattr(NODE_MODULE, "evaluate_scope_alignment", spy)

    evaluate_seniority_node(state, normalization=normalization)

    assert received["candidate_evidence"] == tuple(
        item.scope_evidence for item in normalization.scope_evidence
    )
    assert received["jd_evidence"] == tuple(
        item.to_evaluation_evidence()
        for item in normalization.jd_scope_evidence
    )
    assert received["provenance_refs"] == (
        "candidate-provenance",
        "jd-provenance",
    )


def test_missing_candidate_scope_is_excluded_not_penalized() -> None:
    state = _state_with_provenance()
    normalization = _normalization(candidate=())

    result = evaluate_seniority_node(state, normalization=normalization)

    assert result.scope_alignment is not None
    evaluation = result.scope_alignment.seniority_evaluation
    assert evaluation.resolution is DimensionResolution.EXCLUDED
    assert evaluation.exclusion_reason is ExclusionReason.INSUFFICIENT_EVIDENCE
    assert evaluation.raw_value is None
    assert result.scope_alignment.review_required is False


def test_material_jd_contradiction_is_preserved_for_policy_review() -> None:
    state = _state_with_provenance()
    jd = (
        _jd_scope("jd-own-support", ScopeEvidenceCategory.OWNERSHIP),
        _jd_scope(
            "jd-own-contradiction",
            ScopeEvidenceCategory.OWNERSHIP,
            polarity=ScopeEvidencePolarity.CONTRADICTING,
        ),
    )

    result = evaluate_seniority_node(
        state,
        normalization=_normalization(jd=jd),
    )

    assert result.scope_alignment is not None
    assert result.scope_alignment.review_required is True
    assert result.jd_scope_evaluation is not None
    assert result.jd_scope_evaluation.review_required is True
    assert result.jd_scope_evaluation.contradiction_evidence_refs == (
        "jd-own-contradiction",
    )
    assert len(result.pending_reviews) == 1
    request = result.pending_reviews[0]
    assert request.blocking is True
    assert request.evidence_refs == (
        "jd-own-support",
        "jd-own-contradiction",
    )
    assert request.contradiction_refs == ("jd-own-contradiction",)


def test_evidence_and_provenance_references_are_preserved() -> None:
    result = evaluate_seniority_node(
        _state_with_provenance(),
        normalization=_normalization(),
    )

    assert result.scope_alignment is not None
    evaluation = result.scope_alignment.seniority_evaluation
    assert evaluation.evidence_refs == (
        "candidate-ownership",
        "candidate-decisions",
    )
    assert evaluation.provenance_refs == (
        "candidate-provenance",
        "jd-provenance",
    )
    assert result.jd_scope_evaluation is not None
    assert result.jd_scope_evaluation.evidence_refs == (
        "jd-ownership",
        "jd-decisions",
        "jd-production",
    )
    assert result.jd_scope_evaluation.provenance_refs == ("jd-provenance",)


def test_invalid_screening_state_is_rejected() -> None:
    with pytest.raises(SeniorityEvaluationNodeError, match="ScreeningState"):
        evaluate_seniority_node(
            object(),  # type: ignore[arg-type]
            normalization=_normalization(),
        )


def test_screening_identity_mismatch_is_rejected() -> None:
    with pytest.raises(SeniorityEvaluationNodeError, match="screening_id"):
        evaluate_seniority_node(
            _state_with_provenance(),
            normalization=_normalization(screening_id="other-screening"),
        )


def test_invalid_normalization_and_unknown_provenance_are_rejected() -> None:
    with pytest.raises(SeniorityEvaluationNodeError, match="NormalizationResult"):
        evaluate_seniority_node(
            _state_with_provenance(),
            normalization=object(),  # type: ignore[arg-type]
        )

    invalid = _normalization(
        candidate=(
            _candidate_scope(
                "candidate-ownership",
                ScopeEvidenceCategory.OWNERSHIP,
                provenance_ref="missing-provenance",
            ),
        )
    )
    with pytest.raises(SeniorityEvaluationNodeError, match="unknown provenance"):
        evaluate_seniority_node(_state_with_provenance(), normalization=invalid)


def test_missing_jd_scope_evidence_fails_on_required_provenance_contract() -> None:
    with pytest.raises(SeniorityEvaluationNodeError, match="provenance"):
        evaluate_seniority_node(
            _state_with_provenance(),
            normalization=_normalization(jd=()),
        )


def test_evaluator_errors_are_translated_to_node_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(**kwargs):
        raise ValueError("scope classifier rejected evidence")

    monkeypatch.setattr(NODE_MODULE, "evaluate_scope_alignment", fail)

    with pytest.raises(
        SeniorityEvaluationNodeError,
        match="deterministic seniority evaluation failed",
    ):
        evaluate_seniority_node(
            _state_with_provenance(),
            normalization=_normalization(),
        )


def test_review_output_and_assessment_are_deterministic() -> None:
    state = _state_with_provenance()
    normalization = _normalization(
        jd=(
            _jd_scope("jd-support", ScopeEvidenceCategory.OWNERSHIP),
            _jd_scope(
                "jd-contradiction",
                ScopeEvidenceCategory.OWNERSHIP,
                polarity=ScopeEvidencePolarity.CONTRADICTING,
            ),
        )
    )

    first = evaluate_seniority_node(state, normalization=normalization)
    second = evaluate_seniority_node(state, normalization=normalization)

    assert first.scope_alignment is not None
    assert second.scope_alignment is not None
    assert first.scope_alignment.model_dump(
        exclude={"seniority_evaluation": {"created_at"}}
    ) == (
        second.scope_alignment.model_dump(
            exclude={"seniority_evaluation": {"created_at"}}
        )
    )
    assert first.jd_scope_evaluation == second.jd_scope_evaluation
    assert len(first.pending_reviews) == len(second.pending_reviews) == 1
    assert first.pending_reviews[0].model_dump(exclude={"created_at"}) == (
        second.pending_reviews[0].model_dump(exclude={"created_at"})
    )
