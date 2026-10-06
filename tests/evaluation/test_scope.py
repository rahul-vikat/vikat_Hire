from __future__ import annotations

import pytest

from vikat_hire.contracts.common import ScopeLevel
from vikat_hire.contracts.scope import (
    ScopeEvidence,
    ScopeEvidenceCategory,
)
from vikat_hire.evaluation.scope import (
    classify_scope_level,
    satisfied_scope_levels,
    supporting_scope_categories,
)


def evidence(
    evidence_id: str,
    *categories: ScopeEvidenceCategory,
    supervision_learning: bool = False,
) -> ScopeEvidence:
    return ScopeEvidence(
        evidence_id=evidence_id,
        categories=categories,
        supervision_learning=supervision_learning,
        explicit_text=f"Evidence {evidence_id}",
        provenance_refs=(f"source-{evidence_id}",),
    )


def test_l0_requires_explicit_supervision_or_learning() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                supervision_learning=True,
            ),
        )
    )

    assert result == ScopeLevel.L0


def test_empty_evidence_is_unresolved() -> None:
    assert classify_scope_level(evidence=()) is None


def test_l1_requires_ownership() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.OWNERSHIP,
            ),
        )
    )

    assert result == ScopeLevel.L1


def test_production_evidence_alone_does_not_create_l1() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
        )
    )

    assert result is None


def test_l2_requires_independent_ownership_and_decision_evidence() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        )
    )

    assert result == ScopeLevel.L2


def test_l2_is_not_created_by_one_evidence_item_with_two_categories() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.OWNERSHIP,
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        )
    )

    assert result == ScopeLevel.L1


def test_l3_requires_three_independent_required_signals() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
            evidence(
                "e3",
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
        )
    )

    assert result == ScopeLevel.L3


def test_l3_does_not_require_architecture_as_anchor() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
            evidence(
                "e3",
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
        )
    )

    assert result == ScopeLevel.L3


def test_l4_requires_cross_team_and_decision_authority() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.CROSS_TEAM_SCOPE,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        )
    )

    assert result == ScopeLevel.L4


def test_l4_supporting_evidence_does_not_replace_required_gate() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.ARCHITECTURE,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.PEOPLE_LEADERSHIP,
            ),
            evidence(
                "e3",
                ScopeEvidenceCategory.OWNERSHIP,
            ),
        )
    )

    assert result == ScopeLevel.L1


def test_l5_requires_strategy_and_architecture() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.ENGINEERING_STRATEGY,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.ARCHITECTURE,
            ),
        )
    )

    assert result == ScopeLevel.L5


def test_highest_satisfied_level_wins() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
            evidence(
                "e3",
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
            evidence(
                "e4",
                ScopeEvidenceCategory.CROSS_TEAM_SCOPE,
            ),
        )
    )

    assert result == ScopeLevel.L4


def test_l5_beats_all_lower_levels() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.ENGINEERING_STRATEGY,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.ARCHITECTURE,
            ),
            evidence(
                "e3",
                ScopeEvidenceCategory.CROSS_TEAM_SCOPE,
            ),
            evidence(
                "e4",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        )
    )

    assert result == ScopeLevel.L5


def test_supervision_does_not_force_l0_when_higher_level_is_evidenced() -> None:
    result = classify_scope_level(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.OWNERSHIP,
                supervision_learning=True,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        )
    )

    assert result == ScopeLevel.L2


def test_satisfied_levels_are_deterministic() -> None:
    result = satisfied_scope_levels(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        )
    )

    assert result == (
        ScopeLevel.L1,
        ScopeLevel.L2,
    )


def test_supporting_categories_are_reported() -> None:
    result = supporting_scope_categories(
        evidence=(
            evidence(
                "e1",
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            evidence(
                "e2",
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
            evidence(
                "e3",
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
        ),
        level=ScopeLevel.L2,
    )

    assert result == (
        ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
    )

def test_duplicate_evidence_ids_fail_loudly() -> None:
    duplicate = evidence(
        "same",
        ScopeEvidenceCategory.OWNERSHIP,
    )

    with pytest.raises(ValueError, match="IDs must be unique"):
        classify_scope_level(
            evidence=(duplicate, duplicate),
        )


def test_classifier_is_repeatable() -> None:
    input_evidence = (
        evidence(
            "e1",
            ScopeEvidenceCategory.OWNERSHIP,
        ),
        evidence(
            "e2",
            ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
        ),
        evidence(
            "e3",
            ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
        ),
    )

    first = classify_scope_level(evidence=input_evidence)
    second = classify_scope_level(evidence=input_evidence)

    assert first == second == ScopeLevel.L3