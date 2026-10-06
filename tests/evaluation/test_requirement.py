from decimal import Decimal

import pytest

from vikat_hire.contracts.common import MatchStatus
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.matching import KeywordMatch
from vikat_hire.evaluation.requirement import (
    RequirementEvaluationError,
    evaluate_requirement,
)


def claim(
    claim_id: str = "claim-1",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        subject="candidate",
        predicate="has_skill",
        value="Python",
        provenance_refs=("provenance-resume",),
    )


def match(
    *,
    status: MatchStatus,
    score: str,
    candidate_claim_id: str | None = "claim-1",
) -> KeywordMatch:
    return KeywordMatch(
        match_id="match-1",
        requirement_id="req-1",
        candidate_claim_id=candidate_claim_id,
        matched_text="Python",
        canonical_skill_ref="python",
        match_type="exact",
        status=status,
        score=Decimal(score),
        provenance_refs=("provenance-match",),
    )


def test_matched_requirement_is_evaluated() -> None:
    result = evaluate_requirement(
        requirement_id="req-1",
        matches=(
            match(
                status=MatchStatus.MATCHED,
                score="100",
            ),
        ),
        candidate_claims=(claim(),),
    )

    assert result.status is MatchStatus.MATCHED
    assert result.raw_score == Decimal("100")
    assert result.evidence_refs == (
        "provenance-match",
        "provenance-resume",
    )


def test_partial_requirement_preserves_deterministic_score() -> None:
    result = evaluate_requirement(
        requirement_id="req-1",
        matches=(
            match(
                status=MatchStatus.PARTIAL,
                score="60",
            ),
        ),
        candidate_claims=(claim(),),
    )

    assert result.status is MatchStatus.PARTIAL
    assert result.raw_score == Decimal("60")


def test_not_matched_is_real_zero() -> None:
    result = evaluate_requirement(
        requirement_id="req-1",
        matches=(
            match(
                status=MatchStatus.NOT_MATCHED,
                score="0",
            ),
        ),
        candidate_claims=(claim(),),
    )

    assert result.status is MatchStatus.NOT_MATCHED
    assert result.raw_score == Decimal("0")


def test_no_evidence_is_unresolved_not_negative() -> None:
    result = evaluate_requirement(
        requirement_id="req-1",
        matches=(),
        candidate_claims=(),
    )

    assert result.status is MatchStatus.UNRESOLVED
    assert result.raw_score == Decimal("0")
    assert result.evidence_refs == ()


def test_unrelated_match_is_ignored() -> None:
    unrelated = KeywordMatch(
        match_id="match-other",
        requirement_id="req-other",
        candidate_claim_id="claim-1",
        matched_text="Java",
        canonical_skill_ref="java",
        match_type="exact",
        status=MatchStatus.MATCHED,
        score=Decimal("100"),
        provenance_refs=("provenance-other",),
    )

    result = evaluate_requirement(
        requirement_id="req-1",
        matches=(unrelated,),
        candidate_claims=(claim(),),
    )

    assert result.status is MatchStatus.UNRESOLVED


def test_unknown_candidate_claim_fails_loudly() -> None:
    with pytest.raises(
        RequirementEvaluationError,
        match="unknown candidate claim",
    ):
        evaluate_requirement(
            requirement_id="req-1",
            matches=(
                match(
                    status=MatchStatus.MATCHED,
                    score="100",
                    candidate_claim_id="does-not-exist",
                ),
            ),
            candidate_claims=(claim(),),
        )


def test_blank_requirement_id_fails_loudly() -> None:
    with pytest.raises(
        RequirementEvaluationError,
        match="requirement_id must not be blank",
    ):
        evaluate_requirement(
            requirement_id=" ",
            matches=(),
            candidate_claims=(),
        )


def test_highest_match_is_selected_deterministically() -> None:
    lower = KeywordMatch(
        match_id="match-low",
        requirement_id="req-1",
        candidate_claim_id="claim-1",
        matched_text="Python",
        canonical_skill_ref="python",
        match_type="synonym",
        status=MatchStatus.PARTIAL,
        score=Decimal("60"),
        provenance_refs=("provenance-low",),
    )

    higher = KeywordMatch(
        match_id="match-high",
        requirement_id="req-1",
        candidate_claim_id="claim-1",
        matched_text="Python",
        canonical_skill_ref="python",
        match_type="exact",
        status=MatchStatus.MATCHED,
        score=Decimal("100"),
        provenance_refs=("provenance-high",),
    )

    result = evaluate_requirement(
        requirement_id="req-1",
        matches=(lower, higher),
        candidate_claims=(claim(),),
    )

    assert result.status is MatchStatus.MATCHED
    assert result.raw_score == Decimal("100")