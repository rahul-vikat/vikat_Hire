from __future__ import annotations

from vikat_hire.research._ids import deterministic_id


def test_deterministic_id_encodes_component_boundaries() -> None:
    assert deterministic_id("a\x1fb", "c") != deterministic_id("a", "b\x1fc")
    assert deterministic_id("same", "parts") == deterministic_id("same", "parts")
