from __future__ import annotations

from copy import deepcopy

import pytest

from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    ExtractionKind,
    NormalizationResult,
)
from vikat_hire.orchestration.nodes.apply_normalization import (
    ApplyNormalizationNodeError,
    apply_normalization_node,
)
from vikat_hire.orchestration.nodes.normalize import normalize_node
from vikat_hire.orchestration.state import (
    from_orchestration_state,
    to_orchestration_state,
)


def _jd_block(
    *,
    screening_id: str,
    text: str,
) -> ExtractedTextBlock:
    return ExtractedTextBlock(
        block_id=f"{screening_id}:jd:block",
        source_type=SourceType.JD_FILE,
        source_ref=f"{screening_id}:jd",
        text=text,
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=("jd-provenance",),
    )


def _resume_block(
    *,
    screening_id: str,
    text: str,
) -> ExtractedTextBlock:
    return ExtractedTextBlock(
        block_id=f"{screening_id}:resume:block",
        source_type=SourceType.RESUME_FILE,
        source_ref=f"{screening_id}:resume",
        text=text,
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=("resume-provenance",),
    )


def _normalized_transport(screening_state):
    blocks = (
        _jd_block(
            screening_id=screening_state.screening_id,
            text="Must have: Python",
        ),
        _resume_block(
            screening_id=screening_state.screening_id,
            text=(
                "Skills: Python, FastAPI\n"
                "I built backend services."
            ),
        ),
    )

    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=blocks,
    )

    return normalize_node(transport)


def test_apply_normalization_materializes_claims(
    screening_state,
):
    transport = _normalized_transport(screening_state)

    result = apply_normalization_node(transport)

    state, blocks, normalization = from_orchestration_state(
        result
    )

    assert blocks == (
        _jd_block(
            screening_id=screening_state.screening_id,
            text="Must have: Python",
        ),
        _resume_block(
            screening_id=screening_state.screening_id,
            text=(
                "Skills: Python, FastAPI\n"
                "I built backend services."
            ),
        ),
    )

    assert isinstance(normalization, NormalizationResult)

    assert len(normalization.claims) == 1
    assert len(state.claims) == 1

    assert state.claims[0] == normalization.claims[0].claim


def test_apply_normalization_preserves_existing_claims(
    screening_state,
):
    existing_claim = screening_state.claims

    transport = _normalized_transport(screening_state)

    result = apply_normalization_node(transport)

    state, _, normalization = from_orchestration_state(
        result
    )

    assert normalization is not None
    assert state.claims[: len(existing_claim)] == existing_claim
    assert state.claims[len(existing_claim) :] == tuple(
        item.claim
        for item in normalization.claims
    )


def test_apply_normalization_preserves_screening_identity(
    screening_state,
):
    transport = _normalized_transport(screening_state)

    result = apply_normalization_node(transport)

    state, _, normalization = from_orchestration_state(
        result
    )

    assert state.screening_id == screening_state.screening_id
    assert normalization is not None
    assert normalization.screening_id == screening_state.screening_id


def test_apply_normalization_does_not_modify_normalization_artifact(
    screening_state,
):
    transport = _normalized_transport(screening_state)

    before = deepcopy(transport["normalization"])

    result = apply_normalization_node(transport)

    assert result["normalization"] == before


def test_apply_normalization_requires_normalization(
    screening_state,
):
    blocks = (
        _jd_block(
            screening_id=screening_state.screening_id,
            text="Must have: Python",
        ),
        _resume_block(
            screening_id=screening_state.screening_id,
            text="Skills: Python",
        ),
    )

    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=blocks,
    )

    with pytest.raises(
        ApplyNormalizationNodeError,
        match="before normalization",
    ):
        apply_normalization_node(transport)


def test_apply_normalization_rejects_mismatched_normalization(
    screening_state,
):
    transport = _normalized_transport(screening_state)

    invalid = deepcopy(transport)

    assert invalid["normalization"] is not None

    invalid["normalization"]["screening_id"] = "other-screening"

    with pytest.raises(Exception, match="normalization"):
        apply_normalization_node(invalid)


def test_apply_normalization_rejects_duplicate_existing_claim(
    screening_state,
):
    transport = _normalized_transport(screening_state)

    _, _, normalization = from_orchestration_state(
        transport
    )

    assert normalization is not None
    assert normalization.claims

    existing_claim = normalization.claims[0].claim

    state = screening_state.model_copy(
        update={
            "claims": (existing_claim,),
        }
    )

    transport_with_existing_claim = to_orchestration_state(
        state,
        extracted_blocks=(
            _jd_block(
                screening_id=screening_state.screening_id,
                text="Must have: Python",
            ),
            _resume_block(
                screening_id=screening_state.screening_id,
                text=(
                    "Skills: Python, FastAPI\n"
                    "I built backend services."
                ),
            ),
        ),
        normalization=normalization,
    )

    with pytest.raises(
        ApplyNormalizationNodeError,
        match="already exist",
    ):
        apply_normalization_node(
            transport_with_existing_claim
        )


def test_apply_normalization_rejects_duplicate_claims_in_normalization(
    screening_state,
):
    transport = _normalized_transport(screening_state)

    _, _, normalization = from_orchestration_state(
        transport
    )

    assert normalization is not None
    assert normalization.claims

    duplicated_claims = (
        normalization.claims[0],
        normalization.claims[0],
    )

    invalid_normalization = normalization.model_copy(
        update={
            "claims": duplicated_claims,
        }
    )

    invalid_transport = to_orchestration_state(
        screening_state,
        extracted_blocks=normalization.extracted_blocks,
        normalization=invalid_normalization,
    )

    with pytest.raises(
        ApplyNormalizationNodeError,
        match="duplicate claim ids",
    ):
        apply_normalization_node(
            invalid_transport
        )


def test_apply_normalization_is_checkpoint_roundtrip_safe(
    screening_state,
):
    transport = _normalized_transport(screening_state)

    result = apply_normalization_node(transport)

    first = from_orchestration_state(result)
    second = from_orchestration_state(
        deepcopy(result)
    )

    assert first == second
