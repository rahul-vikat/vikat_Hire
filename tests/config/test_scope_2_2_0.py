from __future__ import annotations

import pytest
from pydantic import ValidationError

from vikat_hire.config.scope_2_2_0 import (
    SCOPE_TAXONOMY_2_2_0,
    SCOPE_TAXONOMY_VERSION_2_2_0,
    get_scope_taxonomy_2_2_0,
)
from vikat_hire.contracts.common import ScopeLevel
from vikat_hire.contracts.scope import (
    ScopeEvidence,
    ScopeEvidenceCategory,
    ScopeGate,
    ScopeTaxonomyConfiguration,
)


def test_authoritative_taxonomy_version() -> None:
    assert SCOPE_TAXONOMY_VERSION_2_2_0 == "2.2.0"
    assert SCOPE_TAXONOMY_2_2_0.taxonomy_version == "2.2.0"


def test_taxonomy_contains_exactly_l0_to_l5() -> None:
    levels = {gate.level for gate in SCOPE_TAXONOMY_2_2_0.gates}

    assert levels == {
        ScopeLevel.L0,
        ScopeLevel.L1,
        ScopeLevel.L2,
        ScopeLevel.L3,
        ScopeLevel.L4,
        ScopeLevel.L5,
    }


def test_l0_uses_attribute_not_new_category() -> None:
    l0 = next(
        gate for gate in SCOPE_TAXONOMY_2_2_0.gates
        if gate.level == ScopeLevel.L0
    )

    assert l0.requires_supervision_learning is True
    assert l0.required_categories == ()
    assert l0.supporting_categories == ()


def test_exactly_seven_evidence_categories() -> None:
    assert {category.value for category in ScopeEvidenceCategory} == {
        "ownership",
        "technical_decision_authority",
        "architecture",
        "people_leadership",
        "cross_team_scope",
        "production_operational_ownership",
        "engineering_strategy",
    }


def test_scope_evidence_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        ScopeEvidence(
            evidence_id="ev-1",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
            explicit_text="Owned the feature end to end.",
            provenance_refs=(),
        )


def test_scope_evidence_rejects_duplicate_categories() -> None:
    with pytest.raises(ValidationError):
        ScopeEvidence(
            evidence_id="ev-1",
            categories=(
                ScopeEvidenceCategory.OWNERSHIP,
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            explicit_text="Owned the feature end to end.",
            provenance_refs=("resume-1",),
        )


def test_scope_gate_rejects_required_supporting_overlap() -> None:
    with pytest.raises(ValueError):
        ScopeGate(
            level=ScopeLevel.L2,
            required_categories=(
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            supporting_categories=(
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            rationale="Invalid overlapping gate.",
        )


def test_taxonomy_is_immutable() -> None:
    with pytest.raises(ValidationError):
        SCOPE_TAXONOMY_2_2_0.taxonomy_version = "legacy"


def test_taxonomy_rejects_non_authoritative_version() -> None:
    with pytest.raises(ValidationError):
        ScopeTaxonomyConfiguration(
            taxonomy_version="2.1.0",
            gates=SCOPE_TAXONOMY_2_2_0.gates,
        )


def test_taxonomy_accessor_returns_authoritative_configuration() -> None:
    assert get_scope_taxonomy_2_2_0() == SCOPE_TAXONOMY_2_2_0


def test_l2_gate_requires_ownership_and_decision_authority() -> None:
    l2 = next(
        gate for gate in SCOPE_TAXONOMY_2_2_0.gates
        if gate.level == ScopeLevel.L2
    )

    assert l2.required_categories == (
        ScopeEvidenceCategory.OWNERSHIP,
        ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
    )


def test_l3_gate_requires_production_responsibility() -> None:
    l3 = next(
        gate for gate in SCOPE_TAXONOMY_2_2_0.gates
        if gate.level == ScopeLevel.L3
    )

    assert (
        ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP
        in l3.required_categories
    )


def test_l4_gate_requires_cross_team_scope() -> None:
    l4 = next(
        gate for gate in SCOPE_TAXONOMY_2_2_0.gates
        if gate.level == ScopeLevel.L4
    )

    assert ScopeEvidenceCategory.CROSS_TEAM_SCOPE in l4.required_categories


def test_l5_gate_requires_strategy_and_architecture() -> None:
    l5 = next(
        gate for gate in SCOPE_TAXONOMY_2_2_0.gates
        if gate.level == ScopeLevel.L5
    )

    assert ScopeEvidenceCategory.ENGINEERING_STRATEGY in l5.required_categories
    assert ScopeEvidenceCategory.ARCHITECTURE in l5.required_categories