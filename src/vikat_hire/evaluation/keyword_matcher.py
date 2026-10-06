from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from vikat_hire.contracts.common import MatchStatus
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.matching import KeywordMatch


class KeywordMatchingError(ValueError):
    """Raised when deterministic keyword matching input is invalid."""


@dataclass(frozen=True)
class KeywordDefinition:
    """
    Canonical deterministic vocabulary entry.

    All aliases must be explicitly configured.
    """

    canonical_ref: str
    keywords: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    abbreviations: tuple[str, ...] = ()
    technology_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class RequirementKeyword:
    """
    Normalized representation of one JD requirement.
    """

    requirement_id: str
    text: str
    vocabulary: KeywordDefinition | None = None


_MATCH_SCORES: dict[str, Decimal] = {
    "exact": Decimal("100"),
    "phrase": Decimal("100"),
    "synonym": Decimal("95"),
    "abbreviation": Decimal("95"),
    "technology_alias": Decimal("95"),
    "normalized": Decimal("90"),
}


def match_requirement(
    *,
    requirement: RequirementKeyword,
    claims: tuple[Claim, ...],
) -> tuple[KeywordMatch, ...]:
    """
    Deterministically match one JD requirement against candidate claims.

    Matching precedence:

        exact
        phrase
        synonym
        abbreviation
        technology_alias
        normalized

    The strongest deterministic match for each candidate claim is retained.
    """

    _validate_requirement(requirement)

    if not claims:
        return ()

    requirement_text = _normalize_text(requirement.text)

    if not requirement_text:
        return ()

    candidates = _candidate_terms(requirement)

    results: list[KeywordMatch] = []

    for claim in claims:
        claim_text = _normalize_text(_claim_text(claim))

        if not claim_text:
            continue

        match_type = _find_match_type(
            requirement_text=requirement_text,
            claim_text=claim_text,
            candidates=candidates,
        )

        if match_type is None:
            continue

        results.append(
            KeywordMatch(
                match_id=(
                    f"{requirement.requirement_id}:"
                    f"{claim.claim_id}:"
                    f"{match_type}"
                ),
                requirement_id=requirement.requirement_id,
                candidate_claim_id=claim.claim_id,
                matched_text=_claim_text(claim),
                canonical_skill_ref=(
                    requirement.vocabulary.canonical_ref
                    if requirement.vocabulary is not None
                    else None
                ),
                match_type=match_type,
                status=MatchStatus.MATCHED,
                score=_MATCH_SCORES[match_type],
                provenance_refs=claim.provenance_refs,
            )
        )

    return tuple(results)


def _validate_requirement(
    requirement: RequirementKeyword,
) -> None:
    if not requirement.requirement_id.strip():
        raise KeywordMatchingError(
            "requirement_id must not be blank"
        )

    if not requirement.text.strip():
        raise KeywordMatchingError(
            "requirement text must not be blank"
        )


def _candidate_terms(
    requirement: RequirementKeyword,
) -> tuple[tuple[str, str], ...]:
    """
    Return explicitly configured candidate terms.

    Each tuple is:

        (normalized_term, match_type)
    """

    terms: list[tuple[str, str]] = []

    # The requirement itself is always an exact candidate.
    terms.append(
        (_normalize_text(requirement.text), "exact")
    )

    vocabulary = requirement.vocabulary

    if vocabulary is None:
        return tuple(terms)

    for value in vocabulary.keywords:
        terms.append((_normalize_text(value), "exact"))

    for value in vocabulary.synonyms:
        terms.append((_normalize_text(value), "synonym"))

    for value in vocabulary.abbreviations:
        terms.append((_normalize_text(value), "abbreviation"))

    for value in vocabulary.technology_aliases:
        terms.append((_normalize_text(value), "technology_alias"))

    return tuple(
        (term, match_type)
        for term, match_type in terms
        if term
    )


def _find_match_type(
    *,
    requirement_text: str,
    claim_text: str,
    candidates: tuple[tuple[str, str], ...],
) -> str | None:
    """
    Determine the strongest deterministic match.

    Exact token/phrase matches are checked before weaker normalized
    matching.
    """

    # Exact normalized phrase.
    if claim_text == requirement_text:
        return "exact"

    # Full configured phrase/token match.
    for candidate, match_type in candidates:
        if _contains_phrase(
            haystack=claim_text,
            needle=candidate,
        ):
            return match_type

    # Controlled normalized/stemmed comparison.
    requirement_stems = _stem_tokens(requirement_text)
    claim_stems = _stem_tokens(claim_text)

    if requirement_stems and requirement_stems == claim_stems:
        return "normalized"

    if (
        len(requirement_stems) == 1
        and requirement_stems[0] in claim_stems
    ):
        return "normalized"

    return None


def _claim_text(claim: Claim) -> str:
    value = claim.value

    if isinstance(value, str):
        return value

    return str(value)


def _normalize_text(value: str) -> str:
    """
    Normalize deterministic comparison text.

    This intentionally does not use fuzzy matching.
    """

    value = value.casefold()
    value = value.replace("-", " ")
    value = value.replace("_", " ")
    value = re.sub(r"[^\w\s+#./]", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def _contains_phrase(
    *,
    haystack: str,
    needle: str,
) -> bool:
    if not needle:
        return False

    pattern = (
        r"(?<![\w+#.])"
        + re.escape(needle)
        + r"(?![\w+#.])"
    )

    return re.search(pattern, haystack) is not None


def _stem_tokens(value: str) -> tuple[str, ...]:
    """
    Small deterministic suffix normalizer.

    This is deliberately conservative. It is not an ML stemmer.
    """

    tokens = value.split()

    normalized: list[str] = []

    for token in tokens:
        token = token.strip()

        if len(token) > 5 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 5 and token.endswith("ing"):
            token = token[:-3]
        elif len(token) > 4 and token.endswith("ed"):
            token = token[:-2]
        elif len(token) > 4 and token.endswith("es"):
            token = token[:-2]
        elif len(token) > 3 and token.endswith("s"):
            token = token[:-1]

        normalized.append(token)

    return tuple(normalized)