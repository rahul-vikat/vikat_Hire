from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import model_validator

from ..contracts.common import ContractModel
from ..contracts.state import ScreeningState


class Checkpoint(ContractModel):
    """
    Domain checkpoint for resuming one screening execution.

    This contract deliberately does not define backend, serialization,
    locking, retry, or concurrency semantics.
    """

    screening_id: str
    revision: int
    current_node: str
    state: ScreeningState
    created_at: datetime

    @model_validator(mode="after")
    def validate_identity(self) -> Checkpoint:
        if self.screening_id != self.state.screening_id:
            raise ValueError(
                "checkpoint screening_id must match state screening_id"
            )

        if self.revision != self.state.revision:
            raise ValueError(
                "checkpoint revision must match state revision"
            )

        return self


class CheckpointStore(Protocol):
    """
    Typed persistence boundary for screening checkpoints.

    Implementations are responsible only for persistence. They must not
    evaluate, score, apply policy, normalize, or otherwise mutate the
    screening domain state.
    """

    def save(self, checkpoint: Checkpoint) -> None:
        """Persist a checkpoint."""
        ...

    def load_latest(self, screening_id: str) -> Checkpoint | None:
        """Load the latest persisted checkpoint, or None when absent."""
        ...