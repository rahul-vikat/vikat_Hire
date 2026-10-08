from __future__ import annotations

from copy import deepcopy

import pytest

from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.normalization import (
    ExtractionKind,
    ExtractedTextBlock,
    NormalizationResult,
)
from vikat_hire.orchestration.nodes.normalize import (
    NormalizationNodeError,
    normalize_node,
)
from vikat_hire.orchestration.state import (
    from_orchestration_state,
    to_orchestration_state,
)


def _transport(screening_state, extracted_blocks):
    return to_orchestration_state(
        screening_state,
        extracted_blocks=extracted_blocks,
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


def test_normalize_node_creates_authoritative_normalization(
    screening_state,
):
    blocks = (
        _jd_block(
            screening_id=screening_state.screening_id,
            text=(
                "Must have: Python\n"
                "Must have: FastAPI"
            ),
        ),
        _resume_block(
            screening_id=screening_state.screening_id,
            text=(
                "Skills: Python, FastAPI\n"
                "Worked as Software Engineer at Acme "
                "2022-01 - Present."
            ),
        ),
    )

    result = normalize_node(
        _transport(screening_state, blocks)
    )

    state, decoded_blocks, normalization = from_orchestration_state(
        result
    )

    assert state == screening_state
    assert decoded_blocks == blocks

    assert isinstance(normalization, NormalizationResult)
    assert normalization.screening_id == screening_state.screening_id

    assert len(normalization.jd_requirements) == 2
    assert len(normalization.skills) == 2
    assert len(normalization.experience_records) == 1

    assert all(
        requirement.source_type is SourceType.JD_FILE
        for requirement in normalization.jd_requirements
    )

    assert all(
        skill.source_type is SourceType.RESUME_FILE
        for skill in normalization.skills
    )


def test_normalize_node_does_not_normalize_jd_as_candidate(
    screening_state,
):
    blocks = (
        _jd_block(
            screening_id=screening_state.screening_id,
            text="Must have: Python",
        ),
        _resume_block(
            screening_id=screening_state.screening_id,
            text="Skills: FastAPI",
        ),
    )

    result = normalize_node(
        _transport(screening_state, blocks)
    )

    _, _, normalization = from_orchestration_state(result)

    assert normalization is not None
    assert normalization.jd_requirements
    assert normalization.skills

    assert all(
        skill.source_type is SourceType.RESUME_FILE
        for skill in normalization.skills
    )


def test_normalize_node_requires_jd(
    screening_state,
):
    blocks = (
        _resume_block(
            screening_id=screening_state.screening_id,
            text="Skills: Python",
        ),
    )

    with pytest.raises(
        NormalizationNodeError,
        match="without JD extracted blocks",
    ):
        normalize_node(
            _transport(screening_state, blocks)
        )


def test_normalize_node_requires_resume(
    screening_state,
):
    blocks = (
        _jd_block(
            screening_id=screening_state.screening_id,
            text="Must have: Python",
        ),
    )

    with pytest.raises(
        NormalizationNodeError,
        match="without resume extracted blocks",
    ):
        normalize_node(
            _transport(screening_state, blocks)
        )


def test_normalize_node_requires_extracted_blocks(
    screening_state,
):
    with pytest.raises(
        NormalizationNodeError,
        match="without extracted text blocks",
    ):
        normalize_node(
            _transport(screening_state, ())
        )


def test_normalization_is_checkpoint_roundtrip_safe(
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

    result = normalize_node(
        _transport(screening_state, blocks)
    )

    first = from_orchestration_state(result)
    second = from_orchestration_state(deepcopy(result))

    assert first == second
    assert first[2] is not None


def test_normalize_node_rejects_mismatched_normalization_payload(
    screening_state,
    extracted_blocks,
):
    transport = to_orchestration_state(
        screening_state,
        extracted_blocks=extracted_blocks,
    )

    invalid = deepcopy(transport)
    invalid["normalization"] = {
        "screening_id": "other-screening",
    }

    with pytest.raises(Exception, match="normalization"):
        normalize_node(invalid)