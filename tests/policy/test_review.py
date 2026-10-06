from __future__ import annotations

from decimal import Decimal

from vikat_hire.contracts.common import DimensionResolution, ReviewReason, ScopeLevel
from vikat_hire.contracts.evaluation import ScopeAlignmentAssessment, SeniorityScopeEvaluation
from vikat_hire.contracts.scope import JDScopeEvaluation
from vikat_hire.policy.review import build_scope_review_requests


def _alignment(review_required: bool = False) -> ScopeAlignmentAssessment:
    seniority = SeniorityScopeEvaluation(candidate_level=ScopeLevel.L2, required_level=ScopeLevel.L3, resolution=DimensionResolution.EVALUATED, delta=-1, raw_value=Decimal("75"), evidence_refs=("candidate-ownership",), provenance_refs=("candidate-source",), rationale="Candidate scope is one level below required scope.")
    return ScopeAlignmentAssessment(seniority_evaluation=seniority, review_required=review_required, review_reason="Scope review is required." if review_required else None)


def _jd(review_required: bool = False) -> JDScopeEvaluation:
    return JDScopeEvaluation(required_level=None if review_required else ScopeLevel.L3, resolution="unresolved" if review_required else "evaluated", review_required=review_required, evidence_refs=("jd-ownership", "jd-contradiction"), contradiction_evidence_refs=("jd-contradiction",) if review_required else (), provenance_refs=("jd-source",), rationale="Material contradiction requires review." if review_required else "JD scope was deterministically evaluated.")


def test_material_jd_contradiction_creates_blocking_review() -> None:
    request = build_scope_review_requests(jd_scope_evaluation=_jd(True), scope_alignment=_alignment())[0]
    assert request.reason is ReviewReason.CONTRADICTION
    assert request.blocking is True
    assert request.evidence_refs == ("jd-ownership", "jd-contradiction")
    assert request.contradiction_refs == ("jd-contradiction",)


def test_non_contradictory_scope_creates_no_review() -> None:
    assert build_scope_review_requests(jd_scope_evaluation=_jd(), scope_alignment=_alignment()) == ()


def test_scope_alignment_review_does_not_invent_contradiction() -> None:
    assert build_scope_review_requests(jd_scope_evaluation=_jd(), scope_alignment=_alignment(True)) == ()


def test_review_does_not_change_seniority_score() -> None:
    alignment = _alignment(True)
    requests = build_scope_review_requests(jd_scope_evaluation=_jd(True), scope_alignment=alignment)
    assert len(requests) == 1
    assert alignment.seniority_evaluation.raw_value == Decimal("75")


def test_review_output_is_deterministic() -> None:
    first = build_scope_review_requests(jd_scope_evaluation=_jd(True), scope_alignment=_alignment())
    second = build_scope_review_requests(jd_scope_evaluation=_jd(True), scope_alignment=_alignment())
    assert tuple(x.model_dump(exclude={"review_id", "created_at"}) for x in first) == tuple(x.model_dump(exclude={"review_id", "created_at"}) for x in second)
