from __future__ import annotations

from collections.abc import Iterable

from vikat_hire.config.scope_2_2_0 import SCOPE_TAXONOMY_2_2_0
from vikat_hire.contracts.common import ScopeLevel
from vikat_hire.contracts.scope import (
    JDScopeEvidence,
    JDScopeEvaluation,
    ScopeEvidenceCategory,
    ScopeEvidencePolarity,
)


_SCOPE_ORDER = (
    ScopeLevel.L0,
    ScopeLevel.L1,
    ScopeLevel.L2,
    ScopeLevel.L3,
    ScopeLevel.L4,
    ScopeLevel.L5,
)


_INDEPENDENT_SCOPE_CATEGORIES = frozenset(
    {
        ScopeEvidenceCategory.OWNERSHIP,
        ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
        ScopeEvidenceCategory.ARCHITECTURE,
        ScopeEvidenceCategory.PEOPLE_LEADERSHIP,
        ScopeEvidenceCategory.CROSS_TEAM_SCOPE,
        ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
        ScopeEvidenceCategory.ENGINEERING_STRATEGY,
    }
)


def _validate_evidence(
    evidence: tuple[JDScopeEvidence, ...],
) -> None:
    evidence_ids = [item.evidence_id for item in evidence]

    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("JD scope evidence IDs must be unique")


def _supporting_evidence(
    evidence: tuple[JDScopeEvidence, ...],
) -> tuple[JDScopeEvidence, ...]:
    return tuple(
        item
        for item in evidence
        if item.polarity == ScopeEvidencePolarity.SUPPORTING
    )


def _contradicting_evidence(
    evidence: tuple[JDScopeEvidence, ...],
) -> tuple[JDScopeEvidence, ...]:
    return tuple(
        item
        for item in evidence
        if item.polarity == ScopeEvidencePolarity.CONTRADICTING
    )


def _material_contradiction_refs(
    evidence: tuple[JDScopeEvidence, ...],
) -> tuple[str, ...]:
    """
    Detect material semantic contradictions.

    Rules:
    1. Supporting and contradicting evidence for the same category conflict.
    2. Contradicting supervision/learning conflicts with supporting
       independent-scope evidence.
    3. Unrelated categories do not conflict merely because their polarity
       differs.
    """
    supporting = _supporting_evidence(evidence)
    contradicting = _contradicting_evidence(evidence)

    contradictory_refs: set[str] = set()

    supporting_categories = {
        category
        for item in supporting
        for category in item.categories
    }

    for item in contradicting:
        if any(
            category in supporting_categories
            for category in item.categories
        ):
            contradictory_refs.add(item.evidence_id)

    supporting_independent_scope = any(
        item.supervision_learning is False
        and any(
            category in _INDEPENDENT_SCOPE_CATEGORIES
            for category in item.categories
        )
        for item in supporting
    )

    contradicting_supervision = any(
        item.supervision_learning
        for item in contradicting
    )

    if contradicting_supervision and supporting_independent_scope:
        contradictory_refs.update(
            item.evidence_id
            for item in contradicting
            if item.supervision_learning
        )

        contradictory_refs.update(
            item.evidence_id
            for item in supporting
            if any(
                category in _INDEPENDENT_SCOPE_CATEGORIES
                for category in item.categories
            )
        )

    return tuple(
        item.evidence_id
        for item in evidence
        if item.evidence_id in contradictory_refs
    )


def _category_evidence(
    evidence: tuple[JDScopeEvidence, ...],
    category: ScopeEvidenceCategory,
) -> tuple[JDScopeEvidence, ...]:
    return tuple(
        item
        for item in evidence
        if item.polarity == ScopeEvidencePolarity.SUPPORTING
        and category in item.categories
    )


def _required_categories_satisfied(
    evidence: tuple[JDScopeEvidence, ...],
    required_categories: tuple[ScopeEvidenceCategory, ...],
) -> bool:
    if not required_categories:
        return True

    candidates_by_category = {
        category: _category_evidence(evidence, category)
        for category in required_categories
    }

    if any(
        not candidates
        for candidates in candidates_by_category.values()
    ):
        return False

    ordered_categories = sorted(
        required_categories,
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


def _l0_satisfied(
    evidence: tuple[JDScopeEvidence, ...],
) -> bool:
    return any(
        item.polarity == ScopeEvidencePolarity.SUPPORTING
        and item.supervision_learning
        for item in evidence
    )


def _gate_satisfied(
    evidence: tuple[JDScopeEvidence, ...],
    level: ScopeLevel,
) -> bool:
    gate = next(
        gate
        for gate in SCOPE_TAXONOMY_2_2_0.gates
        if gate.level == level
    )

    if level == ScopeLevel.L0:
        return _l0_satisfied(evidence)

    if (
        gate.requires_supervision_learning
        and not _l0_satisfied(evidence)
    ):
        return False

    return _required_categories_satisfied(
        evidence,
        gate.required_categories,
    )


def classify_required_scope_level(
    *,
    evidence: Iterable[JDScopeEvidence],
) -> JDScopeEvaluation:
    """
    Deterministically classify the required JD scope level.

    Material contradictions produce unresolved scope and require review.
    Otherwise the highest satisfied authoritative 2.2.0 gate wins.
    """
    evidence_tuple = tuple(evidence)

    _validate_evidence(evidence_tuple)

    evidence_refs = tuple(
        item.evidence_id
        for item in evidence_tuple
    )

    provenance_refs = tuple(
        dict.fromkeys(
            provenance_ref
            for item in evidence_tuple
            for provenance_ref in item.provenance_refs
        )
    )

    if not provenance_refs:
        raise ValueError(
            "JD scope classification requires provenance references"
        )

    contradiction_refs = _material_contradiction_refs(
        evidence_tuple,
    )

    if contradiction_refs:
        return JDScopeEvaluation(
            required_level=None,
            resolution="unresolved",
            review_required=True,
            evidence_refs=evidence_refs,
            contradiction_evidence_refs=contradiction_refs,
            provenance_refs=provenance_refs,
            rationale=(
                "Materially contradictory JD scope evidence was detected; "
                "required scope is unresolved and requires review."
            ),
        )

    for level in reversed(_SCOPE_ORDER):
        if _gate_satisfied(evidence_tuple, level):
            return JDScopeEvaluation(
                required_level=level,
                resolution="evaluated",
                review_required=False,
                evidence_refs=evidence_refs,
                contradiction_evidence_refs=(),
                provenance_refs=provenance_refs,
                rationale=(
                    f"Highest satisfied JD scope gate is "
                    f"{level.value}."
                ),
            )

    return JDScopeEvaluation(
        required_level=None,
        resolution="unresolved",
        review_required=False,
        evidence_refs=evidence_refs,
        contradiction_evidence_refs=(),
        provenance_refs=provenance_refs,
        rationale=(
            "JD evidence does not satisfy any authoritative scope gate."
        ),
    )