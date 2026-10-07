from __future__ import annotations

from datetime import datetime, timezone
from typing import get_type_hints

import pytest

from vikat_hire.contracts.inputs import (
    DocumentInput,
    ExternalSourceInput,
    ScreeningInput,
)
from vikat_hire.contracts.common import InputKind
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.persistence import (
    Checkpoint,
    CheckpointStore,
    ScreeningStateStore,
)


def make_screening_state() -> ScreeningState:
    screening_input = ScreeningInput(
        screening_id="screening-1",
        jd=DocumentInput(
            input_id="jd-1",
            kind=InputKind.JD,
            filename="jd.pdf",
            media_type="application/pdf",
            content_hash="jd-hash",
            storage_ref="jd-ref",
        ),
        resume=DocumentInput(
            input_id="resume-1",
            kind=InputKind.RESUME,
            filename="resume.pdf",
            media_type="application/pdf",
            content_hash="resume-hash",
            storage_ref="resume-ref",
        ),
        external_sources=ExternalSourceInput(),
    )

    return ScreeningState(
        screening_id="screening-1",
        screening_input=screening_input,
        revision=7,
    )


def test_checkpoint_preserves_screening_state() -> None:
    state = make_screening_state()

    checkpoint = Checkpoint(
        screening_id=state.screening_id,
        revision=state.revision,
        current_node=state.current_node,
        state=state,
        created_at=datetime.now(timezone.utc),
    )

    assert checkpoint.screening_id == state.screening_id
    assert checkpoint.revision == state.revision
    assert checkpoint.current_node == state.current_node
    assert checkpoint.state == state


def test_checkpoint_requires_matching_screening_id() -> None:
    state = make_screening_state()

    with pytest.raises(
        ValueError,
        match="checkpoint screening_id must match state screening_id",
    ):
        Checkpoint(
            screening_id="different-screening",
            revision=state.revision,
            current_node=state.current_node,
            state=state,
            created_at=datetime.now(timezone.utc),
        )


def test_checkpoint_requires_matching_revision() -> None:
    state = make_screening_state()

    with pytest.raises(
        ValueError,
        match="checkpoint revision must match state revision",
    ):
        Checkpoint(
            screening_id=state.screening_id,
            revision=state.revision + 1,
            current_node=state.current_node,
            state=state,
            created_at=datetime.now(timezone.utc),
        )


def test_checkpoint_is_immutable() -> None:
    state = make_screening_state()

    checkpoint = Checkpoint(
        screening_id=state.screening_id,
        revision=state.revision,
        current_node=state.current_node,
        state=state,
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(Exception):
        checkpoint.revision = 8


def test_screening_state_store_is_protocol() -> None:
    assert isinstance(ScreeningStateStore, type)
    assert get_type_hints(ScreeningStateStore.save)["state"] is ScreeningState
    assert (
        get_type_hints(ScreeningStateStore.load)["screening_id"] is str
    )


def test_checkpoint_store_is_protocol() -> None:
    assert isinstance(CheckpointStore, type)
    assert (
        get_type_hints(CheckpointStore.save)["checkpoint"] is Checkpoint
    )
    assert (
        get_type_hints(CheckpointStore.load_latest)["screening_id"] is str
    )