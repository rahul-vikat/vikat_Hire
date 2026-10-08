from __future__ import annotations

from hashlib import sha256

from pydantic import ValidationError

from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.evaluation import ScopeAlignmentAssessment
from vikat_hire.contracts.normalization import NormalizationResult
from vikat_hire.contracts.scope import ScopeEvidence
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.jd_scope import classify_required_scope_level
from vikat_hire.evaluation.seniority import evaluate_scope_alignment
from vikat_hire.policy.review import build_scope_review_requests


class SeniorityEvaluationNodeError(ValueError):
    """Raised when scope-evaluation orchestration input is invalid."""


_CANDIDATE_SCOPE_SOURCES = frozenset(
    {
        SourceType.RESUME_FILE,
        SourceType.LINKEDIN,
        SourceType.GITHUB,
        SourceType.PORTFOLIO,
    }
)


def evaluate_seniority_node(
    state: ScreeningState,
    *,
    normalization: NormalizationResult,
) -> ScreeningState:
    """Bridge normalized candidate/JD scope evidence into deterministic evaluation.

    The node stores the dedicated scope assessment and JD scope result on
    ScreeningState. It does not add seniority to the intermediate/final
    EvaluationResult or calculate a weighted screening score.
    """
    if not isinstance(state, ScreeningState):
        raise SeniorityEvaluationNodeError("state must be a ScreeningState")
    if not isinstance(normalization, NormalizationResult):
        raise SeniorityEvaluationNodeError(
            "normalization must be a NormalizationResult"
        )
    try:
        normalization = NormalizationResult.model_validate(
            normalization.model_dump()
        )
    except ValidationError as exc:
        raise SeniorityEvaluationNodeError(
            f"invalid normalization: {exc}"
        ) from exc

    if state.screening_input.screening_id != state.screening_id:
        raise SeniorityEvaluationNodeError(
            "input screening_id does not match state screening_id"
        )
    if normalization.screening_id != state.screening_id:
        raise SeniorityEvaluationNodeError(
            "normalization screening_id does not match state screening_id"
        )

    candidate_records = normalization.scope_evidence
    candidate_evidence: list[ScopeEvidence] = []
    for record in candidate_records:
        if record.source_type not in _CANDIDATE_SCOPE_SOURCES:
            raise SeniorityEvaluationNodeError(
                "candidate scope evidence has an unsupported source type: "
                f"{record.source_type.value!r}"
            )
        candidate_evidence.append(record.scope_evidence)

    jd_evidence = tuple(
        item.to_evaluation_evidence()
        for item in normalization.jd_scope_evidence
    )

    provenance_refs = _ordered_unique(
        reference
        for item in (*candidate_records, *normalization.jd_scope_evidence)
        for reference in item.provenance_refs
    )
    known_provenance_refs = {
        item.provenance_id for item in state.provenances
    }
    unknown_refs = set(provenance_refs) - known_provenance_refs
    if unknown_refs:
        raise SeniorityEvaluationNodeError(
            "scope evidence references unknown provenance: "
            f"{sorted(unknown_refs)}"
        )
    if not provenance_refs:
        raise SeniorityEvaluationNodeError(
            "scope evaluation requires candidate or JD evidence provenance"
        )

    try:
        jd_scope_evaluation = classify_required_scope_level(
            evidence=jd_evidence
        )
        seniority_evaluation, review_required = evaluate_scope_alignment(
            candidate_evidence=tuple(candidate_evidence),
            jd_evidence=jd_evidence,
            provenance_refs=provenance_refs,
        )
        if review_required != jd_scope_evaluation.review_required:
            raise SeniorityEvaluationNodeError(
                "seniority evaluator and JD scope classifier returned "
                "inconsistent review signals"
            )
        assessment = ScopeAlignmentAssessment(
            seniority_evaluation=seniority_evaluation,
            review_required=review_required,
            review_reason=(
                "Material JD scope contradiction requires human review."
                if review_required
                else None
            ),
        )
        review_requests = build_scope_review_requests(
            jd_scope_evaluation=jd_scope_evaluation,
            scope_alignment=assessment,
        )
    except SeniorityEvaluationNodeError:
        raise
    except (ValueError, ValidationError) as exc:
        raise SeniorityEvaluationNodeError(
            f"deterministic seniority evaluation failed: {exc}"
        ) from exc

    stable_reviews = tuple(
        _stable_review_request(
            request=request,
            screening_id=state.screening_id,
            updated_at=state.updated_at,
        )
        for request in review_requests
    )
    pending_by_id = {item.review_id: item for item in state.pending_reviews}
    pending_by_id.update({item.review_id: item for item in stable_reviews})

    return state.model_copy(
        update={
            "scope_alignment": assessment,
            "jd_scope_evaluation": jd_scope_evaluation,
            "pending_reviews": tuple(pending_by_id.values()),
        }
    )


def _ordered_unique(values) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise SeniorityEvaluationNodeError(
                "scope evidence provenance references must be non-empty strings"
            )
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _stable_review_request(*, request, screening_id: str, updated_at):
    payload = "\x1f".join(
        (
            screening_id,
            request.reason.value,
            *request.evidence_refs,
            *request.contradiction_refs,
        )
    )
    return request.model_copy(
        update={
            "review_id": "scope-review-" + sha256(payload.encode()).hexdigest(),
            "created_at": updated_at,
        }
    )
