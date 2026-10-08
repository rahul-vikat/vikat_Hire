from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    MatchStatus,
    RequirementCategory,
    RequirementImportance,
    SourceType,
)
from vikat_hire.contracts.matching import SemanticMatch
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.evaluation.semantic_fit import (
    SemanticFitAggregationError,
    aggregate_semantic_fit,
)


def _requirement(requirement_id: str, index: int = 1) -> JDRequirement:
    return JDRequirement(
        requirement_id=requirement_id,
        category=RequirementCategory.SKILL,
        importance=RequirementImportance.MUST_HAVE,
        text=f"Requirement {requirement_id}",
        source_type=SourceType.JD_FILE,
        source_ref="jd-1",
        evidence_refs=(f"jd-evidence-{index}",),
        provenance_refs=(f"jd-provenance-{index}",),
    )


def _match(
    requirement_id: str,
    *,
    match_id: str,
    status: MatchStatus,
    score: str = "0",
    provenance_refs: tuple[str, ...] = ("candidate-provenance",),
) -> SemanticMatch:
    return SemanticMatch(
        match_id=match_id,
        requirement_id=requirement_id,
        status=status,
        score=Decimal(score),
        rationale=f"Deterministic match for {requirement_id}.",
        provenance_refs=provenance_refs,
    )


def test_matched_partial_and_not_matched_use_arithmetic_mean() -> None:
    result = aggregate_semantic_fit(
        requirements=tuple(_requirement(f"req-{i}", i) for i in range(1, 4)),
        matches=(
            _match("req-1", match_id="match-1", status=MatchStatus.MATCHED, score="90"),
            _match("req-2", match_id="match-2", status=MatchStatus.PARTIAL, score="60"),
            _match("req-3", match_id="match-3", status=MatchStatus.NOT_MATCHED),
        ),
    )

    assert result.dimension is DimensionName.SEMANTIC_FIT
    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("50.00")


def test_unresolved_match_is_excluded_from_mean() -> None:
    result = aggregate_semantic_fit(
        requirements=(_requirement("req-1"), _requirement("req-2", 2)),
        matches=(
            _match("req-1", match_id="match-1", status=MatchStatus.MATCHED, score="80"),
            _match("req-2", match_id="match-2", status=MatchStatus.UNRESOLVED),
        ),
    )

    assert result.raw_value == Decimal("80.00")
    assert result.requirement_refs == ("req-1", "req-2")


def test_all_unresolved_matches_produce_excluded_dimension() -> None:
    result = aggregate_semantic_fit(
        requirements=(_requirement("req-1"),),
        matches=(
            _match("req-1", match_id="match-1", status=MatchStatus.UNRESOLVED),
        ),
    )

    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.exclusion_reason is ExclusionReason.INSUFFICIENT_EVIDENCE


def test_not_matched_is_zero_and_remains_in_denominator() -> None:
    result = aggregate_semantic_fit(
        requirements=(_requirement("req-1"), _requirement("req-2", 2)),
        matches=(
            _match("req-1", match_id="match-1", status=MatchStatus.MATCHED, score="100"),
            _match("req-2", match_id="match-2", status=MatchStatus.NOT_MATCHED, score="50"),
        ),
    )

    assert result.raw_value == Decimal("50.00")


def test_duplicate_requirement_ids_are_rejected() -> None:
    with pytest.raises(SemanticFitAggregationError, match="duplicate requirement ID"):
        aggregate_semantic_fit(
            requirements=(_requirement("req-1"), _requirement("req-1", 2)),
            matches=(),
        )


def test_duplicate_matches_for_requirement_are_rejected() -> None:
    with pytest.raises(
        SemanticFitAggregationError,
        match="duplicate semantic match requirement_id",
    ):
        aggregate_semantic_fit(
            requirements=(_requirement("req-1"),),
            matches=(
                _match("req-1", match_id="match-1", status=MatchStatus.MATCHED, score="70"),
                _match("req-1", match_id="match-2", status=MatchStatus.MATCHED, score="80"),
            ),
        )


def test_unknown_requirement_reference_is_rejected() -> None:
    with pytest.raises(SemanticFitAggregationError, match="unknown requirement"):
        aggregate_semantic_fit(
            requirements=(_requirement("req-1"),),
            matches=(
                _match("unknown", match_id="match-1", status=MatchStatus.MATCHED, score="70"),
            ),
        )


def test_duplicate_match_ids_are_rejected() -> None:
    with pytest.raises(SemanticFitAggregationError, match="unique"):
        aggregate_semantic_fit(
            requirements=(_requirement("req-1"), _requirement("req-2", 2)),
            matches=(
                _match("req-1", match_id="same", status=MatchStatus.MATCHED, score="70"),
                _match("req-2", match_id="same", status=MatchStatus.MATCHED, score="80"),
            ),
        )


def test_score_must_be_a_finite_decimal_in_range() -> None:
    invalid = _match("req-1", match_id="match-1", status=MatchStatus.MATCHED, score="70")
    invalid = invalid.model_copy(update={"score": Decimal("NaN")})

    with pytest.raises(SemanticFitAggregationError, match="finite Decimal"):
        aggregate_semantic_fit(requirements=(_requirement("req-1"),), matches=(invalid,))


def test_mean_uses_decimal_half_up_rounding() -> None:
    result = aggregate_semantic_fit(
        requirements=(_requirement("req-1"), _requirement("req-2", 2)),
        matches=(
            _match("req-1", match_id="match-1", status=MatchStatus.MATCHED, score="1.00"),
            _match("req-2", match_id="match-2", status=MatchStatus.PARTIAL, score="1.01"),
        ),
    )

    assert result.raw_value == Decimal("1.01")


def test_evidence_and_provenance_references_are_preserved() -> None:
    result = aggregate_semantic_fit(
        requirements=(_requirement("req-1"),),
        matches=(
            _match(
                "req-1",
                match_id="match-1",
                status=MatchStatus.MATCHED,
                score="80",
                provenance_refs=("candidate-provenance",),
            ),
        ),
    )

    assert result.evidence_refs == ("jd-evidence-1",)
    assert result.provenance_refs == ("jd-provenance-1", "candidate-provenance")


def test_repeated_semantic_fit_evaluation_is_deterministic() -> None:
    requirements = (_requirement("req-1"),)
    matches = (
        _match("req-1", match_id="match-1", status=MatchStatus.PARTIAL, score="73.456"),
    )
    first = aggregate_semantic_fit(requirements=requirements, matches=matches)
    second = aggregate_semantic_fit(requirements=requirements, matches=matches)

    assert first.model_dump(exclude={"dimension_id", "created_at"}) == second.model_dump(
        exclude={"dimension_id", "created_at"}
    )
