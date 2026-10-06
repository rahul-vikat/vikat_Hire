from __future__ import annotations

from collections.abc import Iterable

from vikat_hire.config.scope_2_2_0 import SCOPE_TAXONOMY_2_2_0
from vikat_hire.contracts.common import ScopeLevel
from vikat_hire.contracts.scope import (
    ScopeEvidence,
    ScopeEvidenceCategory,
    ScopeGate,
)


_SCOPE_ORDER: tuple[ScopeLevel, ...] = (
    ScopeLevel.L0,
    ScopeLevel.L1,
    ScopeLevel.L2,
    ScopeLevel.L3,
    ScopeLevel.L4,
    ScopeLevel.L5,
)


def _validate_evidence(evidence: tuple[ScopeEvidence, ...]) -> None:
    evidence_ids = [item.evidence_id for item in evidence]

    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("scope evidence IDs must be unique")


def _category_evidence(
    evidence: Iterable[ScopeEvidence],
    category: ScopeEvidenceCategory,
) -> tuple[ScopeEvidence, ...]:
    return tuple(
        item
        for item in evidence
        if category in item.categories
    )


def _required_categories_satisfied(
    evidence: tuple[ScopeEvidence, ...],
    gate: ScopeGate,
) -> bool:
    """
    Every required category must have independent evidence.

    A single evidence item cannot satisfy two required categories. This prevents
    one ambiguous statement carrying multiple labels from artificially
    satisfying a multi-signal gate.
    """

    required = gate.required_categories

    if not required:
        return True

    candidates_by_category = {
        category: _category_evidence(evidence, category)
        for category in required
    }

    if any(not candidates for candidates in candidates_by_category.values()):
        return False

    # Deterministically search for an assignment of distinct evidence records
    # to the required categories.
    ordered_categories = sorted(
        required,
        key=lambda category: (
            len(candidates_by_category[category]),
            category.value,
        ),
    )

    def backtrack(
        index: int,
        used_evidence_ids: frozenset[str],
    ) -> bool:
        if index == len(ordered_categories):
            return True

        category = ordered_categories[index]

        for candidate in candidates_by_category[category]:
            if candidate.evidence_id in used_evidence_ids:
                continue

            if backtrack(
                index + 1,
                used_evidence_ids | {candidate.evidence_id},
            ):
                return True

        return False

    return backtrack(0, frozenset())


def _l0_satisfied(evidence: tuple[ScopeEvidence, ...]) -> bool:
    return any(item.supervision_learning for item in evidence)


def _gate_satisfied(
    evidence: tuple[ScopeEvidence, ...],
    gate: ScopeGate,
) -> bool:
    if gate.level == ScopeLevel.L0:
        return _l0_satisfied(evidence)

    if gate.requires_supervision_learning and not _l0_satisfied(evidence):
        return False

    return _required_categories_satisfied(evidence, gate)


def _supporting_categories_present(
    evidence: tuple[ScopeEvidence, ...],
    gate: ScopeGate,
) -> tuple[ScopeEvidenceCategory, ...]:
    return tuple(
        category
        for category in gate.supporting_categories
        if _category_evidence(evidence, category)
    )


def classify_scope_level(
    *,
    evidence: tuple[ScopeEvidence, ...],
) -> ScopeLevel | None:
    """
    Deterministically classify the highest sufficiently evidenced scope level.

    Returns None when no level gate is satisfied.

    This function intentionally does not:
    - calculate a score;
    - inspect job titles;
    - inspect tenure or years of experience;
    - inspect employer prestige;
    - inspect education;
    - use LLM output;
    - infer evidence from absence;
    - accumulate arbitrary weak signals.
    """

    _validate_evidence(evidence)

    for level in reversed(_SCOPE_ORDER):
        gate = next(
            gate
            for gate in SCOPE_TAXONOMY_2_2_0.gates
            if gate.level == level
        )

        if _gate_satisfied(evidence, gate):
            return level

    return None


def satisfied_scope_levels(
    *,
    evidence: tuple[ScopeEvidence, ...],
) -> tuple[ScopeLevel, ...]:
    """
    Return every level whose deterministic gate is satisfied.

    This is primarily useful for audit/testing. The authoritative classification
    is the highest satisfied level returned by classify_scope_level().
    """

    _validate_evidence(evidence)

    satisfied: list[ScopeLevel] = []

    for level in _SCOPE_ORDER:
        gate = next(
            gate
            for gate in SCOPE_TAXONOMY_2_2_0.gates
            if gate.level == level
        )

        if _gate_satisfied(evidence, gate):
            satisfied.append(level)

    return tuple(satisfied)


def supporting_scope_categories(
    *,
    evidence: tuple[ScopeEvidence, ...],
    level: ScopeLevel,
) -> tuple[ScopeEvidenceCategory, ...]:
    """
    Return supporting categories present for a particular configured level.
    """

    _validate_evidence(evidence)

    gate = next(
        (
            gate
            for gate in SCOPE_TAXONOMY_2_2_0.gates
            if gate.level == level
        ),
        None,
    )

    if gate is None:
        raise ValueError(f"unsupported scope level: {level}")

    return _supporting_categories_present(evidence, gate)