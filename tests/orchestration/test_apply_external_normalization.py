from __future__ import annotations

import pytest

from vikat_hire.contracts.common import (
    EvidenceConfidence,
    EvidenceStatus,
    SourceType,
)
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    ExtractionKind,
    NormalizationResult,
    NormalizedClaim,
)
from vikat_hire.orchestration.nodes.apply_external_normalization import (
    ApplyExternalNormalizationNodeError,
    apply_external_normalization_node,
)
from vikat_hire.orchestration.state import (
    from_orchestration_state,
    to_orchestration_state,
)


def _external_block(
    *,
    screening_id: str,
    source_type: SourceType = SourceType.GITHUB,
) -> ExtractedTextBlock:
    source_name = source_type.value

    return ExtractedTextBlock(
        block_id=f"{source_name}-block",
        source_type=source_type,
        source_ref=f"{source_name}-{screening_id}",
        text="Python backend project",
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=(f"{source_name}-provenance",),
    )


def _external_normalization(
    *,
    screening_id: str,
    source_type: SourceType = SourceType.GITHUB,
) -> NormalizationResult:
    source_name = source_type.value
    source_ref = f"{source_name}-{screening_id}"
    provenance_ref = f"{source_name}-provenance"

    claim = Claim(
        claim_id=f"{source_name}-claim",
        subject="candidate",
        predicate="uses",
        value="Python",
        provenance_refs=(provenance_ref,),
    )

    normalized_claim = NormalizedClaim(
        claim=claim,
        source_type=source_type,
        source_ref=source_ref,
        evidence_status=EvidenceStatus.SUPPORTED,
        evidence_refs=(f"{source_name}-evidence",),
        provenance_refs=(provenance_ref,),
        confidence=EvidenceConfidence.HIGH,
    )

    return NormalizationResult(
        screening_id=screening_id,
        claims=(normalized_claim,),
        provenance_refs=(provenance_ref,),
    )


def test_apply_external_normalization_materializes_claim(
    screening_state,
):
    block = _external_block(
        screening_id=screening_state.screening_id,
    )

    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=(block,),
    )

    normalization = _external_normalization(
        screening_id=screening_state.screening_id,
    )

    result = apply_external_normalization_node(
        transport,
        normalization=normalization,
    )

    state, blocks, existing_normalization = (
        from_orchestration_state(result)
    )

    assert blocks == (block,)
    assert existing_normalization is None

    assert len(state.claims) == 1
    assert state.claims[0] == normalization.claims[0].claim


def test_apply_external_normalization_preserves_existing_claims(
    screening_state,
):
    existing_claim = Claim(
        claim_id="resume-claim",
        subject="candidate",
        predicate="worked_with",
        value="FastAPI",
        provenance_refs=("resume-provenance",),
    )

    state = screening_state.model_copy(
        update={
            "claims": (existing_claim,),
        }
    )

    block = _external_block(
        screening_id=state.screening_id,
    )

    transport = to_orchestration_state(
        state,
        extracted_blocks=(block,),
    )

    normalization = _external_normalization(
        screening_id=state.screening_id,
    )

    result = apply_external_normalization_node(
        transport,
        normalization=normalization,
    )

    updated_state, _, _ = from_orchestration_state(result)

    assert updated_state.claims == (
        existing_claim,
        normalization.claims[0].claim,
    )


def test_apply_external_normalization_preserves_resume_normalization(
    screening_state,
):
    existing_normalization = NormalizationResult(
        screening_id=screening_state.screening_id,
    )

    block = _external_block(
        screening_id=screening_state.screening_id,
    )

    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=(block,),
        normalization=existing_normalization,
    )

    external_normalization = _external_normalization(
        screening_id=screening_state.screening_id,
    )

    result = apply_external_normalization_node(
        transport,
        normalization=external_normalization,
    )

    _, _, preserved_normalization = from_orchestration_state(
        result
    )

    assert preserved_normalization == existing_normalization


def test_apply_external_normalization_rejects_mismatched_screening(
    screening_state,
):
    block = _external_block(
        screening_id=screening_state.screening_id,
    )

    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=(block,),
    )

    normalization = _external_normalization(
        screening_id="different-screening",
    )

    with pytest.raises(
        ApplyExternalNormalizationNodeError,
        match="screening_id",
    ):
        apply_external_normalization_node(
            transport,
            normalization=normalization,
        )


def test_apply_external_normalization_rejects_non_external_claim(
    screening_state,
):
    block = _external_block(
        screening_id=screening_state.screening_id,
    )

    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=(block,),
    )

    normalization = NormalizationResult(
        screening_id=screening_state.screening_id,
        claims=(
            NormalizedClaim(
                claim=Claim(
                    claim_id="jd-claim",
                    subject="job",
                    predicate="requires",
                    value="Python",
                    provenance_refs=("jd-provenance",),
                ),
                source_type=SourceType.JD_FILE,
                source_ref="jd-source",
                evidence_status=EvidenceStatus.SUPPORTED,
                evidence_refs=("jd-evidence",),
                provenance_refs=("jd-provenance",),
                confidence=EvidenceConfidence.HIGH,
            ),
        ),
    )

    with pytest.raises(
        ApplyExternalNormalizationNodeError,
        match="non-external claim source",
    ):
        apply_external_normalization_node(
            transport,
            normalization=normalization,
        )


def test_apply_external_normalization_rejects_claim_without_source_block(
    screening_state,
):
    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=(),
    )

    normalization = _external_normalization(
        screening_id=screening_state.screening_id,
    )

    with pytest.raises(
        ApplyExternalNormalizationNodeError,
        match="without an extracted block",
    ):
        apply_external_normalization_node(
            transport,
            normalization=normalization,
        )


def test_apply_external_normalization_rejects_duplicate_existing_claim(
    screening_state,
):
    normalization = _external_normalization(
        screening_id=screening_state.screening_id,
    )

    existing_claim = normalization.claims[0].claim

    state = screening_state.model_copy(
        update={
            "claims": (existing_claim,),
        }
    )

    block = _external_block(
        screening_id=state.screening_id,
    )

    transport = to_orchestration_state(
        state,
        extracted_blocks=(block,),
    )

    with pytest.raises(
        ApplyExternalNormalizationNodeError,
        match="already exist",
    ):
        apply_external_normalization_node(
            transport,
            normalization=normalization,
        )


def test_apply_external_normalization_rejects_duplicate_claims(
    screening_state,
):
    block = _external_block(
        screening_id=screening_state.screening_id,
    )

    base = _external_normalization(
        screening_id=screening_state.screening_id,
    )

    duplicated = base.model_copy(
        update={
            "claims": (
                base.claims[0],
                base.claims[0],
            ),
        }
    )

    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=(block,),
    )

    with pytest.raises(
        ApplyExternalNormalizationNodeError,
        match="duplicate claim id",
    ):
        apply_external_normalization_node(
            transport,
            normalization=duplicated,
        )


def test_apply_external_normalization_supports_linkedin(
    screening_state,
):
    block = _external_block(
        screening_id=screening_state.screening_id,
        source_type=SourceType.LINKEDIN,
    )

    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=(block,),
    )

    normalization = _external_normalization(
        screening_id=screening_state.screening_id,
        source_type=SourceType.LINKEDIN,
    )

    result = apply_external_normalization_node(
        transport,
        normalization=normalization,
    )

    state, _, _ = from_orchestration_state(result)

    assert state.claims == (
        normalization.claims[0].claim,
    )


def test_apply_external_normalization_supports_portfolio(
    screening_state,
):
    block = _external_block(
        screening_id=screening_state.screening_id,
        source_type=SourceType.PORTFOLIO,
    )

    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=(block,),
    )

    normalization = _external_normalization(
        screening_id=screening_state.screening_id,
        source_type=SourceType.PORTFOLIO,
    )

    result = apply_external_normalization_node(
        transport,
        normalization=normalization,
    )

    state, _, _ = from_orchestration_state(result)

    assert state.claims == (
        normalization.claims[0].claim,
    )