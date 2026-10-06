from vikat_hire.contracts.common import ScopeLevel
from vikat_hire.contracts.scope import (
    JDScopeEvidence,
    ScopeEvidenceCategory,
    ScopeEvidencePolarity,
)
from vikat_hire.evaluation.jd_scope import (
    classify_required_scope_level,
)


def _evidence(
    evidence_id: str,
    *,
    categories: tuple[ScopeEvidenceCategory, ...] = (),
    polarity: ScopeEvidencePolarity = ScopeEvidencePolarity.SUPPORTING,
    supervision_learning: bool = False,
    text: str = "Explicit JD scope evidence.",
) -> JDScopeEvidence:
    return JDScopeEvidence(
        evidence_id=evidence_id,
        categories=categories,
        supervision_learning=supervision_learning,
        polarity=polarity,
        explicit_text=text,
        provenance_refs=(f"prov-{evidence_id}",),
    )


def test_jd_l0_requires_explicit_supervision_learning() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "e1",
                supervision_learning=True,
                text="Work under direct supervision while learning the system.",
            ),
        ),
    )

    assert result.required_level == ScopeLevel.L0
    assert result.resolution == "evaluated"
    assert result.review_required is False


def test_jd_l1_requires_ownership() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "e1",
                categories=(ScopeEvidenceCategory.OWNERSHIP,),
            ),
        ),
    )

    assert result.required_level == ScopeLevel.L1


def test_jd_l2_requires_ownership_and_decision_authority() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "ownership",
                categories=(ScopeEvidenceCategory.OWNERSHIP,),
            ),
            _evidence(
                "decision",
                categories=(
                    ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
                ),
            ),
        ),
    )

    assert result.required_level == ScopeLevel.L2


def test_jd_l3_requires_production_anchor() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "ownership",
                categories=(ScopeEvidenceCategory.OWNERSHIP,),
            ),
            _evidence(
                "decision",
                categories=(
                    ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
                ),
            ),
        ),
    )

    assert result.required_level == ScopeLevel.L2


def test_jd_l3_is_reached_with_required_production_evidence() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "ownership",
                categories=(ScopeEvidenceCategory.OWNERSHIP,),
            ),
            _evidence(
                "decision",
                categories=(
                    ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
                ),
            ),
            _evidence(
                "production",
                categories=(
                    ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
                ),
            ),
        ),
    )

    assert result.required_level == ScopeLevel.L3


def test_jd_l4_requires_cross_team_and_decision_authority() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "cross-team",
                categories=(ScopeEvidenceCategory.CROSS_TEAM_SCOPE,),
            ),
            _evidence(
                "decision",
                categories=(
                    ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
                ),
            ),
        ),
    )

    assert result.required_level == ScopeLevel.L4


def test_jd_l5_requires_strategy_and_architecture() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "strategy",
                categories=(ScopeEvidenceCategory.ENGINEERING_STRATEGY,),
            ),
            _evidence(
                "architecture",
                categories=(ScopeEvidenceCategory.ARCHITECTURE,),
            ),
        ),
    )

    assert result.required_level == ScopeLevel.L5


def test_unrelated_polarities_do_not_create_contradiction() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "ownership-support",
                categories=(ScopeEvidenceCategory.OWNERSHIP,),
                polarity=ScopeEvidencePolarity.SUPPORTING,
            ),
            _evidence(
                "architecture-contradiction",
                categories=(ScopeEvidenceCategory.ARCHITECTURE,),
                polarity=ScopeEvidencePolarity.CONTRADICTING,
            ),
        ),
    )

    assert result.required_level == ScopeLevel.L1
    assert result.review_required is False
    assert result.contradiction_evidence_refs == ()


def test_same_category_conflict_is_material() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "ownership-support",
                categories=(ScopeEvidenceCategory.OWNERSHIP,),
                polarity=ScopeEvidencePolarity.SUPPORTING,
            ),
            _evidence(
                "ownership-contradiction",
                categories=(ScopeEvidenceCategory.OWNERSHIP,),
                polarity=ScopeEvidencePolarity.CONTRADICTING,
            ),
        ),
    )

    assert result.required_level is None
    assert result.resolution == "unresolved"
    assert result.review_required is True
    assert result.contradiction_evidence_refs == (
        "ownership-support",
        "ownership-contradiction",
    )


def test_supervision_conflicts_with_independent_scope() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "ownership",
                categories=(ScopeEvidenceCategory.OWNERSHIP,),
                polarity=ScopeEvidencePolarity.SUPPORTING,
            ),
            _evidence(
                "supervision",
                supervision_learning=True,
                polarity=ScopeEvidencePolarity.CONTRADICTING,
                text="The role works under close supervision.",
            ),
        ),
    )

    assert result.required_level is None
    assert result.resolution == "unresolved"
    assert result.review_required is True
    assert result.contradiction_evidence_refs == (
        "ownership",
        "supervision",
    )


def test_supporting_supervision_does_not_conflict_by_itself() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "supervision",
                supervision_learning=True,
                polarity=ScopeEvidencePolarity.SUPPORTING,
            ),
        ),
    )

    assert result.required_level == ScopeLevel.L0
    assert result.review_required is False


def test_contradicting_unrelated_supervision_without_supporting_scope_is_not_review() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "supervision",
                supervision_learning=True,
                polarity=ScopeEvidencePolarity.CONTRADICTING,
            ),
        ),
    )

    assert result.required_level is None
    assert result.resolution == "unresolved"
    assert result.review_required is False


def test_single_evidence_item_cannot_satisfy_two_required_categories() -> None:
    result = classify_required_scope_level(
        evidence=(
            _evidence(
                "combined",
                categories=(
                    ScopeEvidenceCategory.OWNERSHIP,
                    ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
                ),
            ),
        ),
    )

    assert result.required_level == ScopeLevel.L1


def test_duplicate_evidence_ids_fail() -> None:
    try:
        classify_required_scope_level(
            evidence=(
                _evidence(
                    "duplicate",
                    categories=(ScopeEvidenceCategory.OWNERSHIP,),
                ),
                _evidence(
                    "duplicate",
                    categories=(
                        ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
                    ),
                ),
            ),
        )
    except ValueError as exc:
        assert str(exc) == "JD scope evidence IDs must be unique"
    else:
        raise AssertionError("expected duplicate evidence IDs to fail")


def test_provenance_is_merged_and_deduplicated() -> None:
    first = JDScopeEvidence(
        evidence_id="e1",
        categories=(ScopeEvidenceCategory.OWNERSHIP,),
        polarity=ScopeEvidencePolarity.SUPPORTING,
        explicit_text="Own features.",
        provenance_refs=("source-1", "shared"),
    )
    second = JDScopeEvidence(
        evidence_id="e2",
        categories=(
            ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
        ),
        polarity=ScopeEvidencePolarity.SUPPORTING,
        explicit_text="Make local technical decisions.",
        provenance_refs=("shared", "source-2"),
    )

    result = classify_required_scope_level(
        evidence=(first, second),
    )

    assert result.required_level == ScopeLevel.L2
    assert result.provenance_refs == (
        "source-1",
        "shared",
        "source-2",
    )


def test_result_is_deterministic() -> None:
    evidence = (
        _evidence(
            "ownership",
            categories=(ScopeEvidenceCategory.OWNERSHIP,),
        ),
        _evidence(
            "decision",
            categories=(
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
        ),
    )

    first = classify_required_scope_level(evidence=evidence)
    second = classify_required_scope_level(evidence=evidence)

    assert first.model_dump() == second.model_dump()