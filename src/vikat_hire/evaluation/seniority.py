from __future__ import annotations

from decimal import Decimal

from vikat_hire.contracts.common import (
    DimensionResolution,
    ExclusionReason,
    ScopeLevel,
)
from vikat_hire.contracts.evaluation import SeniorityScopeEvaluation


_SCOPE_INDEX: dict[ScopeLevel, int] = {
    ScopeLevel.L0: 0,
    ScopeLevel.L1: 1,
    ScopeLevel.L2: 2,
    ScopeLevel.L3: 3,
    ScopeLevel.L4: 4,
    ScopeLevel.L5: 5,
}


def scope_level_index(level: ScopeLevel) -> int:
    """Return the normalized ordinal for a scope level."""

    try:
        return _SCOPE_INDEX[level]
    except KeyError as exc:
        raise ValueError(f"Unsupported scope level: {level!r}") from exc


def scope_delta(
    candidate_level: ScopeLevel,
    required_level: ScopeLevel,
) -> int:
    """Calculate candidate scope minus required scope."""

    return scope_level_index(candidate_level) - scope_level_index(required_level)


def score_scope_delta(delta: int) -> Decimal:
    """Map a scope delta to the authoritative 0-100 raw score.

    Authoritative mapping:

        delta == 0   -> 100
        delta >= +1  -> 90
        delta == -1  -> 75
        delta == -2  -> 45
        delta <= -3  -> 20
    """

    if delta == 0:
        return Decimal("100")

    if delta >= 1:
        return Decimal("90")

    if delta == -1:
        return Decimal("75")

    if delta == -2:
        return Decimal("45")

    if delta <= -3:
        return Decimal("20")

    raise ValueError(f"Unsupported scope delta: {delta}")


def evaluate_seniority_scope(
    *,
    candidate_level: ScopeLevel | None,
    required_level: ScopeLevel | None,
    evidence_refs: tuple[str, ...] = (),
    provenance_refs: tuple[str, ...],
) -> SeniorityScopeEvaluation:
    """Evaluate candidate scope against the JD-required scope.

    Scope levels must already have been derived and validated upstream.
    This function performs only the deterministic alignment calculation.
    """

    if candidate_level is None or required_level is None:
        return SeniorityScopeEvaluation(
            candidate_level=candidate_level,
            required_level=required_level,
            resolution=DimensionResolution.EXCLUDED,
            evidence_refs=evidence_refs,
            provenance_refs=provenance_refs,
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
            rationale=(
                "Seniority scope alignment was excluded because both "
                "candidate and required scope levels are required."
            ),
        )

    delta = scope_delta(
        candidate_level=candidate_level,
        required_level=required_level,
    )
    raw_value = score_scope_delta(delta)

    return SeniorityScopeEvaluation(
        candidate_level=candidate_level,
        required_level=required_level,
        resolution=DimensionResolution.EVALUATED,
        delta=delta,
        raw_value=raw_value,
        evidence_refs=evidence_refs,
        provenance_refs=provenance_refs,
        rationale=(
            f"Candidate scope {candidate_level.value} has delta {delta} "
            f"against required scope {required_level.value}; "
            f"deterministic scope mapping produced {raw_value}."
        ),
    )