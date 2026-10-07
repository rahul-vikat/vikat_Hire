from __future__ import annotations

import pytest

from vikat_hire.contracts.common import (
    AccessStatus,
    DerivationMethod,
    EvidenceConfidence,
    EvidenceStatus,
    InputKind,
    SourceReliability,
    SourceType,
)
from vikat_hire.contracts.evidence import (
    Claim,
    Evidence,
    Provenance,
)
from vikat_hire.contracts.inputs import (
    DocumentInput,
    ScreeningInput,
)
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.nodes.assemble_evidence import (
    EvidenceAssemblyNodeError,
    assemble_evidence_node,
)


def _state() -> ScreeningState:
    screening_input = ScreeningInput(
        jd=DocumentInput(
            kind=InputKind.JD,
            filename="jd.txt",
            media_type="text/plain",
            content_hash="jd-hash",
            storage_ref="test://jd",
        ),
        resume=DocumentInput(
            kind=InputKind.RESUME,
            filename="resume.txt",
            media_type="text/plain",
            content_hash="resume-hash",
            storage_ref="test://resume",
        ),
    )

    return ScreeningState(
        screening_id=screening_input.screening_id,
        screening_input=screening_input,
    )


def _provenance() -> Provenance:
    return Provenance(
        provenance_id="prov-1",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        method=DerivationMethod.PARSER,
        access_status=AccessStatus.AUTHORIZED,
    )


def _claim() -> Claim:
    return Claim(
        claim_id="claim-1",
        subject="candidate",
        predicate="has_skill",
        value="Python",
        provenance_refs=("prov-1",),
    )


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="evidence-1",
        claim_id="claim-1",
        status=EvidenceStatus.SUPPORTED,
        content={"skill": "Python"},
        provenance_refs=("prov-1",),
        confidence=EvidenceConfidence.HIGH,
        source_reliability=SourceReliability.SELF_REPORTED,
        supports_claim=True,
    )


def test_node_validates_existing_evidence_without_mutating_state() -> None:
    state = _state().model_copy(
        update={
            "claims": (_claim(),),
            "provenances": (_provenance(),),
            "evidence": (_evidence(),),
        }
    )

    result = assemble_evidence_node(state)

    assert result == state


def test_node_preserves_unrelated_state() -> None:
    state = _state().model_copy(
        update={
            "claims": (_claim(),),
            "provenances": (_provenance(),),
            "evidence": (_evidence(),),
            "required_inputs_missing": ("linkedin_url",),
            "errors": ("existing-error",),
            "revision": 7,
        }
    )

    result = assemble_evidence_node(state)

    assert result.required_inputs_missing == state.required_inputs_missing
    assert result.errors == state.errors
    assert result.revision == state.revision
    assert result.screening_input == state.screening_input


def test_node_rejects_invalid_evidence_graph() -> None:
    state = _state().model_copy(
        update={
            "claims": (_claim(),),
            "provenances": (),
            "evidence": (_evidence(),),
        }
    )

    with pytest.raises(
        EvidenceAssemblyNodeError,
        match="unknown provenance",
    ):
        assemble_evidence_node(state)


def test_node_does_not_create_evidence() -> None:
    state = _state()

    result = assemble_evidence_node(state)

    assert result.evidence == ()
    assert result.claims == ()
    assert result.provenances == ()


def test_node_rejects_invalid_state_type() -> None:
    with pytest.raises(
        EvidenceAssemblyNodeError,
        match="state must be a ScreeningState",
    ):
        assemble_evidence_node(object())  # type: ignore[arg-type]