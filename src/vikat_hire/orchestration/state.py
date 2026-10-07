"""Transport immutable domain state through LangGraph without domain imports of it."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, TypedDict

from vikat_hire.contracts.normalization import ExtractedTextBlock
from vikat_hire.contracts.state import ScreeningState


class OrchestrationState(TypedDict):
    # Plain containers avoid requiring a checkpoint serializer to instantiate
    # application-specific Pydantic classes. Domain values (e.g. Decimal) remain
    # Python values for the configured LangGraph serializer to preserve.
    screening_state: dict[str, Any]
    extracted_blocks: list[dict[str, Any]]


class OrchestrationStateError(ValueError):
    """Invalid orchestration transport or inconsistent screening identity."""


def to_orchestration_state(
    state: ScreeningState,
    *,
    extracted_blocks: tuple[ExtractedTextBlock, ...],
) -> OrchestrationState:
    """Create a detached transport; never change revisions or workflow fields."""
    if not isinstance(state, ScreeningState):
        raise OrchestrationStateError("state must be a ScreeningState")
    if any(not isinstance(block, ExtractedTextBlock) for block in extracted_blocks):
        raise OrchestrationStateError("extracted_blocks must contain ExtractedTextBlock objects")
    transport: OrchestrationState = {
        "screening_state": deepcopy(state.model_dump(mode="python")),
        "extracted_blocks": [
            deepcopy(block.model_dump(mode="python")) for block in extracted_blocks
        ],
    }
    from_orchestration_state(transport)
    return transport


def from_orchestration_state(
    transport: OrchestrationState,
) -> tuple[ScreeningState, tuple[ExtractedTextBlock, ...]]:
    """Revalidate complete snapshots, never reconstruct missing state from defaults.

    This boundary accepts the complete transport produced by
    to_orchestration_state, not a partial domain update. Defaulting missing fields
    could discard results, reset revision, or introduce a new timestamp on replay.
    """
    if not isinstance(transport, dict) or set(transport) != {"screening_state", "extracted_blocks"}:
        raise OrchestrationStateError(
            "transport requires screening_state and extracted_blocks only"
        )
    if not isinstance(transport["screening_state"], dict):
        raise OrchestrationStateError("screening_state must be a mapping")
    missing_fields = set(ScreeningState.model_fields) - set(transport["screening_state"])
    if missing_fields:
        raise OrchestrationStateError(
            "screening_state snapshot is missing fields: " + ", ".join(sorted(missing_fields))
        )
    if not isinstance(transport["extracted_blocks"], (tuple, list)) or any(
        not isinstance(block, dict) for block in transport["extracted_blocks"]
    ):
        raise OrchestrationStateError("extracted_blocks must be a sequence of mappings")
    state = ScreeningState.model_validate(deepcopy(transport["screening_state"]))
    blocks = tuple(
        ExtractedTextBlock.model_validate(deepcopy(block))
        for block in transport["extracted_blocks"]
    )
    if not state.screening_id.strip() or not state.current_node.strip():
        raise OrchestrationStateError("screening_id and current_node must not be blank")
    for name in ("screening_input", "evaluation", "score", "policy", "explanation"):
        artifact = getattr(state, name)
        if artifact is not None and artifact.screening_id != state.screening_id:
            raise OrchestrationStateError(f"{name} screening_id does not match state screening_id")
    if any(not key.strip() for key in state.required_inputs_missing):
        raise OrchestrationStateError("required_inputs_missing must not contain blank keys")
    return state, blocks
