from __future__ import annotations

from typing import Protocol

from ..contracts.state import ScreeningState


class ScreeningStateStore(Protocol):
    """
    Typed persistence boundary for a screening's domain state.

    This interface intentionally defines no backend, serialization,
    concurrency, locking, retry, or revision semantics.
    """

    def save(self, state: ScreeningState) -> None:
        """Persist the complete screening state."""
        ...

    def load(self, screening_id: str) -> ScreeningState | None:
        """Load persisted state, or None when the screening is absent."""
        ...