from decimal import Decimal

import pytest

from vikat_hire.config import get_scoring_configuration
from vikat_hire.contracts.common import (
    AccessStatus,
    ApplicabilityStatus,
    DerivationMethod,
    DimensionName,
    DimensionResolution,
    EvidenceConfidence,
    EvidenceStatus,
    InputKind,
    Provenance,
    SourceReliability,
    SourceType,
)
from vikat_hire.contracts.evaluation import DimensionEvaluation, EvaluationResult
from vikat_hire.contracts.evidence import Evidence
from vikat_hire.contracts.explanation import ExplanationResult
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.normalization.document import extract_document_text
from vikat_hire.policy.evaluator import build_mandatory_gates, build_policy_result
from vikat_hire.scoring import calculate_score


@pytest.fixture
def screening_state():
    documents = {
        kind.value: DocumentInput(
            input_id=f"{kind.value}-1",
            kind=kind,
            filename=f"{kind.value}.txt",
            media_type="text/plain",
            content_hash="hash",
            storage_ref=f"store/{kind.value}",
        )
        for kind in (InputKind.JD, InputKind.RESUME)
    }
    provenance = Provenance(
        provenance_id="provenance-1",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        method=DerivationMethod.PARSER,
        access_status=AccessStatus.AUTHORIZED,
        locator={"page": "1"},
    )
    evidence = Evidence(
        evidence_id="evidence-1",
        status=EvidenceStatus.SUPPORTED,
        content={"text": "Python", "nested": {"value": Decimal("12.34")}},
        provenance_refs=(provenance.provenance_id,),
        confidence=EvidenceConfidence.HIGH,
        source_reliability=SourceReliability.SELF_REPORTED,
        supports_claim=True,
    )
    evaluation = EvaluationResult(
        screening_id="screening-1",
        dimensions=(
            DimensionEvaluation(
                dimension=DimensionName.SEMANTIC_FIT,
                applicability=ApplicabilityStatus.APPLICABLE,
                resolution=DimensionResolution.EVALUATED,
                raw_value=Decimal("74.94"),
                evidence_refs=(evidence.evidence_id,),
                provenance_refs=(provenance.provenance_id,),
                rationale="Existing deterministic result",
            ),
        ),
    )
    score = calculate_score(
        screening_id="screening-1",
        evaluations=evaluation.dimensions,
        configuration=get_scoring_configuration("verifyhire-scoring@2.2.0"),
    )
    policy = build_policy_result(
        screening_id="screening-1",
        evaluation=evaluation,
        score=score,
        review_requests=(),
        configuration_ref="policy-1",
        gates=build_mandatory_gates(
            field_presence=dict.fromkeys(
                ("certification", "education", "location", "availability"), True
            ),
            configuration_ref="policy-1",
        ),
    )
    return ScreeningState(
        screening_id="screening-1",
        screening_input=ScreeningInput(
            screening_id="screening-1",
            **documents,
        ),
        current_node="validate_input",
        revision=7,
        provenances=(provenance,),
        evidence=(evidence,),
        evaluation=evaluation,
        score=score,
        policy=policy,
        explanation=ExplanationResult(
            screening_id="screening-1",
            summary="Existing explanation",
            dimensions=(),
            generated_by="test",
            evidence_refs=(evidence.evidence_id,),
        ),
        errors=("existing diagnostic",),
    )


@pytest.fixture
def extracted_blocks(screening_state):
    return tuple(
        block
        for document in (screening_state.screening_input.jd, screening_state.screening_input.resume)
        for block in extract_document_text(
            document=document,
            content=b"Python development",
            provenance_refs=("provenance-1",),
        )
    )
