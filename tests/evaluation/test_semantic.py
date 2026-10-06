from decimal import Decimal

import pytest

from vikat_hire.contracts.common import MatchStatus
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.matching import KeywordMatch
from vikat_hire.evaluation.semantic import (
    SemanticMatchingError,
    match_semantically,
)


def _claim(
    *,
    claim_id: str,
    value: str,
    predicate: str = "skill",
    provenance: tuple[str, ...] = ("prov-1",),
) -> Claim:
    return Claim(
        claim_id=claim_id,
        subject="candidate",
        predicate=predicate,
        value=value,
        provenance_refs=provenance,
    )


def _keyword_match(
    *,
    match_id: str = "km-1",
    requirement_id: str = "req-1",
    claim_id: str | None = "claim-1",
    match_type: str = "exact",
    score: str = "100",
    status: MatchStatus = MatchStatus.MATCHED,
    provenance: tuple[str, ...] = ("prov-1",),
) -> KeywordMatch:
    return KeywordMatch(
        match_id=match_id,
        requirement_id=requirement_id,
        candidate_claim_id=claim_id,
        matched_text="Python",
        canonical_skill_ref="skill:python",
        match_type=match_type,
        status=status,
        score=Decimal(score),
        provenance_refs=provenance,
    )


def test_canonical_skill_reference_is_authoritative() -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=("skill:python",),
        candidate_claims=(
            _claim(
                claim_id="claim-1",
                value="skill:python",
            ),
        ),
        keyword_matches=(),
    )

    assert result.status == MatchStatus.MATCHED
    assert result.score == Decimal("100")
    assert result.candidate_claim_id == "claim-1"
    assert result.provenance_refs == ("prov-1",)


def test_canonical_skill_match_does_not_require_keyword_match() -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=("skill:python",),
        candidate_claims=(
            _claim(
                claim_id="claim-1",
                value="skill:python",
            ),
        ),
        keyword_matches=(),
    )

    assert result.status == MatchStatus.MATCHED


def test_keyword_exact_match_produces_full_score() -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=(
            _claim(
                claim_id="claim-1",
                value="Python",
            ),
        ),
        keyword_matches=(
            _keyword_match(
                match_type="exact",
                score="100",
            ),
        ),
    )

    assert result.status == MatchStatus.MATCHED
    assert result.score == Decimal("100")


@pytest.mark.parametrize(
    ("match_type", "score"),
    [
        ("phrase", "100"),
        ("synonym", "95"),
        ("abbreviation", "95"),
        ("technology_alias", "95"),
        ("normalized", "90"),
    ],
)
def test_keyword_match_strength_is_deterministic(
    match_type: str,
    score: str,
) -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=(
            _claim(
                claim_id="claim-1",
                value="Python",
            ),
        ),
        keyword_matches=(
            _keyword_match(
                match_type=match_type,
                score=score,
            ),
        ),
    )

    assert result.status == MatchStatus.MATCHED
    assert result.score == Decimal(score)


def test_semantic_match_does_not_increase_keyword_score() -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=(
            _claim(
                claim_id="claim-1",
                value="Python",
            ),
        ),
        keyword_matches=(
            _keyword_match(
                match_type="normalized",
                score="100",
            ),
        ),
    )

    assert result.score == Decimal("90")


def test_partial_keyword_match_remains_partial() -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=(
            _claim(
                claim_id="claim-1",
                value="Python",
            ),
        ),
        keyword_matches=(
            _keyword_match(
                status=MatchStatus.PARTIAL,
                match_type="normalized",
                score="90",
            ),
        ),
    )

    assert result.status == MatchStatus.PARTIAL
    assert result.score == Decimal("90")


def test_no_evidence_is_unresolved_not_negative() -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=(),
        keyword_matches=(),
    )

    assert result.status == MatchStatus.UNRESOLVED
    assert result.score == Decimal("0")
    assert result.provenance_refs == ()


def test_unresolved_keyword_match_remains_unresolved() -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=(),
        keyword_matches=(
            _keyword_match(
                claim_id=None,
                status=MatchStatus.UNRESOLVED,
                score="0",
            ),
        ),
    )

    assert result.status == MatchStatus.UNRESOLVED
    assert result.score == Decimal("0")


def test_not_matched_keyword_evidence_is_not_treated_as_missing() -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=(
            _claim(
                claim_id="claim-1",
                value="Java",
            ),
        ),
        keyword_matches=(
            _keyword_match(
                status=MatchStatus.NOT_MATCHED,
                score="0",
            ),
        ),
    )

    assert result.status == MatchStatus.NOT_MATCHED
    assert result.score == Decimal("0")


def test_unrelated_keyword_match_for_different_requirement_is_ignored() -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=(
            _claim(
                claim_id="claim-1",
                value="Python",
            ),
        ),
        keyword_matches=(
            _keyword_match(
                requirement_id="req-2",
                match_id="km-2",
            ),
        ),
    )

    assert result.status == MatchStatus.UNRESOLVED


def test_unknown_candidate_claim_reference_fails_loudly() -> None:
    with pytest.raises(
        SemanticMatchingError,
        match="unknown candidate claim",
    ):
        match_semantically(
            requirement_id="req-1",
            requirement_skill_refs=(),
            candidate_claims=(),
            keyword_matches=(
                _keyword_match(
                    claim_id="missing-claim",
                ),
            ),
        )


def test_duplicate_candidate_claim_ids_fail() -> None:
    claim = _claim(
        claim_id="claim-1",
        value="Python",
    )

    with pytest.raises(
        SemanticMatchingError,
        match="duplicate claim IDs",
    ):
        match_semantically(
            requirement_id="req-1",
            requirement_skill_refs=(),
            candidate_claims=(claim, claim),
            keyword_matches=(),
        )


def test_duplicate_keyword_match_ids_fail() -> None:
    match = _keyword_match(
        match_id="duplicate",
    )

    with pytest.raises(
        SemanticMatchingError,
        match="duplicate match IDs",
    ):
        match_semantically(
            requirement_id="req-1",
            requirement_skill_refs=(),
            candidate_claims=(
                _claim(
                    claim_id="claim-1",
                    value="Python",
                ),
            ),
            keyword_matches=(match, match),
        )


def test_blank_skill_reference_fails_loudly() -> None:
    with pytest.raises(
        SemanticMatchingError,
        match="skill references must not be blank",
    ):
        match_semantically(
            requirement_id="req-1",
            requirement_skill_refs=(" ",),
            candidate_claims=(),
            keyword_matches=(),
        )


def test_unknown_keyword_match_type_fails_loudly() -> None:
    result = _keyword_match(
        match_type="invented_match_type",
        score="100",
    )

    with pytest.raises(
        SemanticMatchingError,
        match="unsupported deterministic keyword match type",
    ):
        match_semantically(
            requirement_id="req-1",
            requirement_skill_refs=(),
            candidate_claims=(
                _claim(
                    claim_id="claim-1",
                    value="Python",
                ),
            ),
            keyword_matches=(result,),
        )


def test_provenance_is_preserved_and_deduplicated() -> None:
    result = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=(
            _claim(
                claim_id="claim-1",
                value="Python",
                provenance=("prov-1", "prov-2"),
            ),
        ),
        keyword_matches=(
            _keyword_match(
                provenance=("prov-2", "prov-3"),
            ),
        ),
    )

    assert result.provenance_refs == (
        "prov-2",
        "prov-3",
    )


def test_same_inputs_produce_same_deterministic_result() -> None:
    claims = (
        _claim(
            claim_id="claim-1",
            value="Python",
        ),
    )
    matches = (
        _keyword_match(
            match_id="km-1",
        ),
    )

    first = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=claims,
        keyword_matches=matches,
    )
    second = match_semantically(
        requirement_id="req-1",
        requirement_skill_refs=(),
        candidate_claims=claims,
        keyword_matches=matches,
    )

    assert first.model_dump(exclude={"created_at"}) == second.model_dump(
        exclude={"created_at"}
    )
