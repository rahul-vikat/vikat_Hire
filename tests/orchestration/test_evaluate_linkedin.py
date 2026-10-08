from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    AccessStatus,
    DerivationMethod,
    EvidenceConfidence,
    EvidenceStatus,
    SourceReliability,
    SourceType,
    DimensionName,
)
from vikat_hire.contracts.evidence import Claim, Evidence
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.contracts.common import InputKind, Provenance
from vikat_hire.evaluation.linkedin_match import (
    evaluate_linkedin_evidence,
)
from vikat_hire.orchestration.nodes.evaluate_linkedin import (
    LinkedInEvaluationNodeError,
    evaluate_linkedin_node,
)


def _screening_state() -> ScreeningState:
    return ScreeningState(
        screening_input=ScreeningInput(
            jd=DocumentInput(
                kind=InputKind.JD,
                filename="jd.txt",
                media_type="text/plain",
                content_hash="jd-hash",
                storage_ref="jd-ref",
            ),
            resume=DocumentInput(
                kind=InputKind.RESUME,
                filename="resume.txt",
                media_type="text/plain",
                content_hash="resume-hash",
                storage_ref="resume-ref",
            ),
        )
    )


def _provenance(
    provenance_id: str,
) -> Provenance:
    return Provenance(
        provenance_id=provenance_id,
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-source",
        method=DerivationMethod.API,
        access_status=AccessStatus.AUTHORIZED,
    )


def _resume_provenance() -> Provenance:
    return Provenance(
        provenance_id="resume-provenance",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-source",
        method=DerivationMethod.PARSER,
        access_status=AccessStatus.AUTHORIZED,
    )


def _claim(
    claim_id: str,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        subject="candidate",
        predicate="has_skill",
        value="Python",
        provenance_refs=("resume-provenance",),
    )


def _evidence(
    *,
    evidence_id: str,
    claim_id: str,
    provenance_id: str,
    status: EvidenceStatus,
    supports_claim: bool,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        claim_id=claim_id,
        status=status,
        content="Python",
        provenance_refs=(provenance_id,),
        confidence=EvidenceConfidence.HIGH,
        source_reliability=SourceReliability.SELF_REPORTED,
        supports_claim=supports_claim,
    )


def test_evaluate_linkedin_node_creates_evaluation() -> None:
    state = _screening_state()

    claim = _claim("claim-1")

    linkedin_provenance = _provenance("linkedin-provenance")

    evidence = _evidence(
        evidence_id="evidence-1",
        claim_id=claim.claim_id,
        provenance_id=linkedin_provenance.provenance_id,
        status=EvidenceStatus.SUPPORTED,
        supports_claim=True,
    )

    state = state.model_copy(
        update={
            "claims": (claim,),
            "provenances": (_resume_provenance(), linkedin_provenance),
            "evidence": (evidence,),
        }
    )

    result = evaluate_linkedin_node(state)

    assert result.evaluation is not None
    assert result.evaluation.screening_id == state.screening_id
    assert len(result.evaluation.dimensions) == 1

    dimension = result.evaluation.dimensions[0]

    assert dimension.dimension is DimensionName.LINKEDIN_EVIDENCE
    assert dimension.raw_value == Decimal("100.00")


def test_evaluate_linkedin_node_preserves_existing_dimensions() -> None:
    state = _screening_state()

    existing = evaluate_linkedin_evidence(
        claims=(),
        evidence=(),
        provenances=(),
        reconciliations=(),
    )

    # The existing evaluation is deliberately constructed separately to
    # verify that the LinkedIn node replaces only its own dimension.
    state = state.model_copy(
        update={
            "evaluation": state.evaluation,
        }
    )

    result = evaluate_linkedin_node(state)

    assert result.evaluation is not None
    assert result.evaluation.dimensions[0].model_dump(
        exclude={"dimension_id", "created_at"}
    ) == existing.model_dump(exclude={"dimension_id", "created_at"})


def test_evaluate_linkedin_node_rejects_mismatched_evaluation() -> None:
    state = _screening_state()

    other_state = _screening_state()

    existing_evaluation = evaluate_linkedin_evidence(
        claims=(),
        evidence=(),
        provenances=(),
        reconciliations=(),
    )

    existing_evaluation_result = state.model_copy(
        update={
            "evaluation": None,
        }
    )

    assert existing_evaluation_result.evaluation is None

    # Construct an evaluation carrying a different screening ID.
    from vikat_hire.contracts.evaluation import EvaluationResult

    mismatched = EvaluationResult(
        screening_id=other_state.screening_id,
        dimensions=(existing_evaluation,),
        deterministic=True,
    )

    state = state.model_copy(
        update={
            "evaluation": mismatched,
        }
    )

    with pytest.raises(
        LinkedInEvaluationNodeError,
        match="evaluation screening_id does not match state screening_id",
    ):
        evaluate_linkedin_node(state)


def test_evaluate_linkedin_node_rejects_invalid_state() -> None:
    with pytest.raises(
        LinkedInEvaluationNodeError,
        match="state must be a ScreeningState",
    ):
        evaluate_linkedin_node("invalid")  # type: ignore[arg-type]
