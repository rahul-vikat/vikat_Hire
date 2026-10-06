from vikat_hire.contracts.common import MatchStatus
from vikat_hire.contracts.evidence import Claim
from vikat_hire.evaluation.keyword_matcher import (
    KeywordDefinition,
    KeywordMatchingError,
    RequirementKeyword,
    match_requirement,
)
import pytest


def claim(
    claim_id: str,
    value: str,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        subject="candidate",
        predicate="has_skill",
        value=value,
        provenance_refs=(f"provenance-{claim_id}",),
    )


def test_exact_keyword_match() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-python",
        text="Python",
    )

    result = match_requirement(
        requirement=requirement,
        claims=(claim("claim-1", "Python"),),
    )

    assert len(result) == 1
    assert result[0].match_type == "exact"
    assert result[0].status is MatchStatus.MATCHED
    assert result[0].score == 100


def test_phrase_match() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-postgres",
        text="PostgreSQL",
    )

    result = match_requirement(
        requirement=requirement,
        claims=(claim("claim-1", "Experienced with PostgreSQL databases"),),
    )

    assert len(result) == 1
    assert result[0].match_type == "exact"


def test_synonym_match() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-database",
        text="database",
        vocabulary=KeywordDefinition(
            canonical_ref="database",
            synonyms=("data store",),
        ),
    )

    result = match_requirement(
        requirement=requirement,
        claims=(claim("claim-1", "Worked with data store systems"),),
    )

    assert len(result) == 1
    assert result[0].match_type == "synonym"


def test_abbreviation_match() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-machine-learning",
        text="machine learning",
        vocabulary=KeywordDefinition(
            canonical_ref="machine-learning",
            abbreviations=("ML",),
        ),
    )

    result = match_requirement(
        requirement=requirement,
        claims=(claim("claim-1", "ML engineering"),),
    )

    assert len(result) == 1
    assert result[0].match_type == "abbreviation"


def test_technology_alias_match() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-postgres",
        text="PostgreSQL",
        vocabulary=KeywordDefinition(
            canonical_ref="postgresql",
            technology_aliases=("postgres",),
        ),
    )

    result = match_requirement(
        requirement=requirement,
        claims=(claim("claim-1", "Postgres administration"),),
    )

    assert len(result) == 1
    assert result[0].match_type == "technology_alias"


def test_normalized_form_match() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-developer",
        text="developer",
    )

    result = match_requirement(
        requirement=requirement,
        claims=(claim("claim-1", "developers"),),
    )

    assert len(result) == 1
    assert result[0].match_type == "normalized"


def test_case_and_separator_normalization() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-data-engineering",
        text="Data Engineering",
    )

    result = match_requirement(
        requirement=requirement,
        claims=(claim("claim-1", "data-engineering"),),
    )

    assert len(result) == 1


def test_unmatched_term_returns_no_match() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-python",
        text="Python",
    )

    result = match_requirement(
        requirement=requirement,
        claims=(claim("claim-1", "Java"),),
    )

    assert result == ()


def test_phrase_boundary_prevents_substring_false_positive() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-java",
        text="Java",
    )

    result = match_requirement(
        requirement=requirement,
        claims=(claim("claim-1", "Javascript developer"),),
    )

    assert result == ()


def test_empty_claims_return_no_match() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-python",
        text="Python",
    )

    assert match_requirement(
        requirement=requirement,
        claims=(),
    ) == ()


def test_blank_requirement_id_fails() -> None:
    with pytest.raises(
        KeywordMatchingError,
        match="requirement_id must not be blank",
    ):
        match_requirement(
            requirement=RequirementKeyword(
                requirement_id=" ",
                text="Python",
            ),
            claims=(),
        )


def test_blank_requirement_text_fails() -> None:
    with pytest.raises(
        KeywordMatchingError,
        match="requirement text must not be blank",
    ):
        match_requirement(
            requirement=RequirementKeyword(
                requirement_id="req-1",
                text=" ",
            ),
            claims=(),
        )


def test_provenance_is_preserved() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-python",
        text="Python",
    )

    result = match_requirement(
        requirement=requirement,
        claims=(claim("claim-1", "Python"),),
    )

    assert result[0].provenance_refs == ("provenance-claim-1",)


def test_same_input_is_deterministic() -> None:
    requirement = RequirementKeyword(
        requirement_id="req-python",
        text="Python",
    )

    claims = (
        claim("claim-1", "Python"),
        claim("claim-2", "Python development"),
    )

    first = match_requirement(
        requirement=requirement,
        claims=claims,
    )

    second = match_requirement(
        requirement=requirement,
        claims=claims,
    )

    assert first == second