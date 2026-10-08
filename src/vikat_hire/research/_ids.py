from __future__ import annotations

import hashlib
import json


def deterministic_id(*parts: str) -> str:
    # JSON array encoding keeps the component boundaries unambiguous even when
    # an input value contains the former delimiter character.
    payload = json.dumps(
        parts,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
