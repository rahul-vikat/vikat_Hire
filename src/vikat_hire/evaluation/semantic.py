from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from vikat_hire.contracts.common import MatchStatus
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.matching import KeywordMatch, SemanticMatch


class SemanticMatchingError(ValueError):
    """Raised when deterministic semantic matching input is invalid."""


_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_QUANT = Decimal("0.01")

# Deterministic evidence strengths.
#
# These values describe the strength of an already-established deterministic
# match. They are not model confidence and are not learned probabilities.
_EXACT_SCORE = Decimal("100")
_SYNONYM_SCORE = Decimal("95")
_ABBREVIATION_SCORE = Decimal("95")
_TECHNOLOGY_ALIAS_SCORE = Decimal("95")
_NORMALIZED_SCORE = Decimal("90")
_PHRASE_SCORE = Decimal("100")

_MATCH_TYPE_SCORE: dict[str, Decimal] = {
    "exact": _EXACT_SCORE,
    "phrase": _PHRASE_SCORE,
    "synonym": _SYNONYM_SCORE,
    "abbreviation": _ABBREVIATION_SCORE,
    "technology_alias": _TECHNOLOGY_ALIAS_SCORE,
    "normalized": _NORMALIZED_SCORE,
}


def match_semantically(
    *,
    requirement_id: str,
    requirement_skill_refs: tuple[str, ...],
    candidate_claims: tuple[Claim, ...],
    keyword_matches: tuple[KeywordMatch, ...],
) -> SemanticMatch:
    """
    Produce one deterministic semantic match for a JD requirement.

    The matcher uses only deterministic inputs:

    1. Explicit canonical-skill-reference intersection.
    2. Previously validated deterministic keyword matches.

    It does not call an LLM, embedding model, external service, or
    probabilistic similarity function.

    The returned SemanticMatch is therefore suitable for the deterministic
    evaluation/scoring path.
    """

    _validate_inputs(
        requirement_id=requirement_id,
        requirement_skill_refs=requirement_skill_refs,
        candidate_claims=candidate_claims,
        keyword_matches=keyword_matches,
    )

    relevant_keyword_matches = tuple(
        match
        for match in keyword_matches
        if match.requirement_id == requirement_id
    )

    claim_by_id = {
        claim.claim_id: claim
        for claim in candidate_claims
    }

    # Only claims actually supplied to this evaluation may be used.
    for match in relevant_keyword_matches:
        if match.candidate_claim_id is not None:
            if match.candidate_claim_id not in claim_by_id:
                raise SemanticMatchingError(
                    "keyword match references an unknown candidate claim: "
                    f"{match.candidate_claim_id}"
                )

    canonical_refs = frozenset(
        ref.strip()
        for ref in requirement_skill_refs
        if ref.strip()
    )

    canonical_matches = _canonical_skill_matches(
        requirement_id=requirement_id,
        requirement_skill_refs=canonical_refs,
        claims=candidate_claims,
    )

    if canonical_matches:
        score = _HUNDRED

        provenance_refs = _unique_refs(
            *(claim.provenance_refs for claim in canonical_matches)
        )

        claim_ids = _unique_claim_ids(canonical_matches)

        return SemanticMatch(
            match_id=_match_id(
                requirement_id=requirement_id,
                candidate_claim_ids=claim_ids,
            ),
            requirement_id=requirement_id,
            candidate_claim_id=claim_ids[0] if len(claim_ids) == 1 else None,
            status=MatchStatus.MATCHED,
            score=score,
            rationale=(
                "Canonical skill reference matched deterministically."
            ),
            provenance_refs=provenance_refs,
        )

    if relevant_keyword_matches:
        return _semantic_match_from_keywords(
            requirement_id=requirement_id,
            keyword_matches=relevant_keyword_matches,
        )

    # No candidate evidence was available for this requirement.
    #
    # This is deliberately UNRESOLVED rather than NOT_MATCHED. Missing
    # evidence is not negative evidence.
    return SemanticMatch(
        match_id=_match_id(
            requirement_id=requirement_id,
            candidate_claim_ids=(),
        ),
        requirement_id=requirement_id,
        candidate_claim_id=None,
        status=MatchStatus.UNRESOLVED,
        score=_ZERO,
        rationale=(
            "No deterministic candidate evidence was available for "
            "semantic evaluation."
        ),
        provenance_refs=(),
    )


def _validate_inputs(
    *,
    requirement_id: str,
    requirement_skill_refs: tuple[str, ...],
    candidate_claims: tuple[Claim, ...],
    keyword_matches: tuple[KeywordMatch, ...],
) -> None:
    if not requirement_id.strip():
        raise SemanticMatchingError(
            "requirement_id must not be blank"
        )

    claim_ids = [claim.claim_id for claim in candidate_claims]

    if len(claim_ids) != len(set(claim_ids)):
        raise SemanticMatchingError(
            "candidate claims must not contain duplicate claim IDs"
        )

    match_ids = [match.match_id for match in keyword_matches]

    if len(match_ids) != len(set(match_ids)):
        raise SemanticMatchingError(
            "keyword matches must not contain duplicate match IDs"
        )

    if any(not ref.strip() for ref in requirement_skill_refs):
        raise SemanticMatchingError(
            "requirement skill references must not be blank"
        )


def _canonical_skill_matches(
    *,
    requirement_id: str,
    requirement_skill_refs: frozenset[str],
    claims: tuple[Claim, ...],
) -> tuple[Claim, ...]:
    if not requirement_skill_refs:
        return ()

    matches: list[Claim] = []

    for claim in claims:
        if claim.predicate.casefold() not in {
            "skill",
            "skills",
            "technology",
            "technology_ref",
            "canonical_skill_ref",
        }:
            continue

        if claim.value.strip() in requirement_skill_refs:
            matches.append(claim)

    return tuple(matches)


def _semantic_match_from_keywords(
    *,
    requirement_id: str,
    keyword_matches: tuple[KeywordMatch, ...],
) -> SemanticMatch:
    usable_matches = tuple(
        match
        for match in keyword_matches
        if match.status
        in {
            MatchStatus.MATCHED,
            MatchStatus.PARTIAL,
        }
    )

    if not usable_matches:
        unresolved_matches = tuple(
            match
            for match in keyword_matches
            if match.status == MatchStatus.UNRESOLVED
        )

        if unresolved_matches:
            return SemanticMatch(
                match_id=_match_id(
                    requirement_id=requirement_id,
                    candidate_claim_ids=(),
                ),
                requirement_id=requirement_id,
                candidate_claim_id=None,
                status=MatchStatus.UNRESOLVED,
                score=_ZERO,
                rationale=(
                    "Deterministic keyword evidence was unresolved; "
                    "no negative semantic conclusion was made."
                ),
                provenance_refs=_unique_refs(
                    *(match.provenance_refs for match in unresolved_matches)
                ),
            )

        return SemanticMatch(
            match_id=_match_id(
                requirement_id=requirement_id,
                candidate_claim_ids=(),
            ),
            requirement_id=requirement_id,
            candidate_claim_id=None,
            status=MatchStatus.NOT_MATCHED,
            score=_ZERO,
            rationale=(
                "Deterministic candidate evidence was evaluated but did "
                "not establish a semantic match."
            ),
            provenance_refs=_unique_refs(
                *(match.provenance_refs for match in keyword_matches)
            ),
        )

    strongest_score = max(
        (
            _keyword_score(match)
            for match in usable_matches
        ),
        default=_ZERO,
    )

    status = (
        MatchStatus.PARTIAL
        if any(
            match.status == MatchStatus.PARTIAL
            for match in usable_matches
        )
        else MatchStatus.MATCHED
    )

    candidate_claim_ids = _unique_candidate_claim_ids(
        usable_matches
    )

    return SemanticMatch(
        match_id=_match_id(
            requirement_id=requirement_id,
            candidate_claim_ids=candidate_claim_ids,
        ),
        requirement_id=requirement_id,
        candidate_claim_id=(
            candidate_claim_ids[0]
            if len(candidate_claim_ids) == 1
            else None
        ),
        status=status,
        score=_quantize_score(strongest_score),
        rationale=(
            "Semantic fit was derived from deterministic keyword evidence "
            "without probabilistic or LLM matching."
        ),
        provenance_refs=_unique_refs(
            *(match.provenance_refs for match in usable_matches)
        ),
    )


def _keyword_score(match: KeywordMatch) -> Decimal:
    configured_score = _MATCH_TYPE_SCORE.get(match.match_type)

    if configured_score is None:
        # The KeywordMatch contract allows a string match_type, so unknown
        # types must not silently become authoritative semantic evidence.
        raise SemanticMatchingError(
            f"unsupported deterministic keyword match type: "
            f"{match.match_type}"
        )

    # Never allow a semantic matcher to increase a validated keyword score.
    return min(match.score, configured_score)


def _maximum_score(*scores: Decimal) -> Decimal:
    if not scores:
        return _ZERO

    return _quantize_score(max(scores))


def _quantize_score(value: Decimal) -> Decimal:
    return value.quantize(
        _QUANT,
        rounding=ROUND_HALF_UP,
    )


def _unique_refs(
    *reference_groups: tuple[str, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []

    for references in reference_groups:
        for reference in references:
            if reference not in seen:
                seen.add(reference)
                result.append(reference)

    return tuple(result)


def _unique_claim_ids(
    claims: tuple[Claim, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []

    for claim in claims:
        if claim.claim_id not in seen:
            seen.add(claim.claim_id)
            result.append(claim.claim_id)

    return tuple(result)


def _unique_candidate_claim_ids(
    matches: tuple[KeywordMatch, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []

    for match in matches:
        if (
            match.candidate_claim_id is not None
            and match.candidate_claim_id not in seen
        ):
            seen.add(match.candidate_claim_id)
            result.append(match.candidate_claim_id)

    return tuple(result)


def _match_id(
    *,
    requirement_id: str,
    candidate_claim_ids: tuple[str, ...],
) -> str:
    claims = ",".join(candidate_claim_ids)
    return f"semantic:{requirement_id}:{claims}"
