"""Replay-safe missing-input interruption; no backend or revision policy."""

from __future__ import annotations

from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict

from vikat_hire.contracts.common import WorkflowStatus, utc_now
from vikat_hire.contracts.inputs import ScreeningInput
from vikat_hire.contracts.normalization import ExtractedTextBlock
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.nodes.validate_input import validate_input_node
from vikat_hire.orchestration.state import (
    OrchestrationState,
    from_orchestration_state,
    to_orchestration_state,
)
from vikat_hire.persistence.checkpoints import Checkpoint


class InputInterruptionError(ValueError):
    """Invalid missing-input checkpoint or resume request."""


class InputResume(BaseModel):
    """Orchestration-only resume payload, passed as a mapping to Command(resume=...).

    The caller supplies complete replacement input metadata and extraction
    output, including retained blocks. No results, revisions, or workflow fields
    may be supplied. This is transport around existing contracts, not extraction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    screening_input: ScreeningInput
    extracted_blocks: tuple[ExtractedTextBlock, ...]


def validate_input_state(transport: OrchestrationState) -> OrchestrationState:
    """Persist this node's returned state before entering the interrupt node.

    A future graph must place this adapter before interrupt_missing_input so its
    checkpoint already explicitly contains WAITING_FOR_INPUT and missing keys.
    """
    state, blocks, normalization = from_orchestration_state(transport)
    validated = validate_input_node(state, extracted_blocks=blocks)
    return to_orchestration_state(
        validated,
        extracted_blocks=blocks,
        normalization=normalization,
    )


def _require_waiting(state: ScreeningState) -> None:
    if state.status is not WorkflowStatus.WAITING_FOR_INPUT or not state.required_inputs_missing:
        raise InputInterruptionError(
            "input interruption requires WAITING_FOR_INPUT and missing keys"
        )


def resume_missing_input(
    transport: OrchestrationState,
    payload: dict,
) -> OrchestrationState:
    """Apply only input data and revalidate; partial input remains waiting."""
    state, _, _ = from_orchestration_state(transport)
    _require_waiting(state)
    if not isinstance(payload, dict):
        raise InputInterruptionError("resume payload must be a mapping")
    supplied = InputResume.model_validate(payload)
    if supplied.screening_input.screening_id != state.screening_id:
        raise InputInterruptionError("resume screening_id does not match interrupted screening")
    updated = state.model_copy(update={"screening_input": supplied.screening_input})
    validated = validate_input_node(updated, extracted_blocks=supplied.extracted_blocks)
    return to_orchestration_state(validated, extracted_blocks=supplied.extracted_blocks)


def interrupt_missing_input(transport: OrchestrationState) -> OrchestrationState:
    """LangGraph node: never return while required input remains missing.

    Requires an externally configured LangGraph checkpointer and thread_id.
    LangGraph replays this node and prior resume values on each resume. Keep it
    side-effect free: persistence writes belong outside this replaying node.
    Partial replies interrupt again, with updated missing keys. Their inputs are
    retained by LangGraph's resume log until this node returns its final update.
    """
    state, _, _ = from_orchestration_state(transport)
    _require_waiting(state)
    while state.required_inputs_missing:
        payload = interrupt(
            {
                "screening_id": state.screening_id,
                "current_node": state.current_node,
                "status": state.status.value,
                "required_inputs_missing": list(state.required_inputs_missing),
                "revision": state.revision,
            }
        )
        transport = resume_missing_input(transport, payload)
        state, _, _ = from_orchestration_state(transport)
    return transport


def create_input_checkpoint(transport: OrchestrationState) -> Checkpoint:
    """Build a domain checkpoint for an injected CheckpointStore to save.

    This contract stores only domain state. Extraction blocks remain in the
    LangGraph transport and must be supplied explicitly on domain-only restore.
    No revision increment, locking, or backend semantics are introduced.
    """
    state, _, _ = from_orchestration_state(transport)
    _require_waiting(state)
    return Checkpoint(
        screening_id=state.screening_id,
        revision=state.revision,
        current_node=state.current_node,
        state=state,
        created_at=utc_now(),
    )


def restore_input_checkpoint(
    checkpoint: Checkpoint,
    *,
    screening_id: str,
    extracted_blocks: tuple[ExtractedTextBlock, ...],
) -> OrchestrationState:
    """Restore a loaded input checkpoint, rejecting identity/node mismatches."""
    if not isinstance(checkpoint, Checkpoint):
        raise InputInterruptionError("checkpoint must be a Checkpoint")
    checkpoint = Checkpoint.model_validate(checkpoint.model_dump(mode="python"))
    if checkpoint.screening_id != screening_id:
        raise InputInterruptionError("checkpoint screening_id does not match requested screening")
    if checkpoint.current_node != checkpoint.state.current_node:
        raise InputInterruptionError("checkpoint current_node does not match state current_node")
    _require_waiting(checkpoint.state)
    return to_orchestration_state(checkpoint.state, extracted_blocks=extracted_blocks)
