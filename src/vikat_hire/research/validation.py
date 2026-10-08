from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from vikat_hire.contracts.research import (
    EntityValidationDecision,
    EntityValidationReason,
    EntityValidationStatus,
    IdentitySignal,
    RawResearchResult,
    ResearchEntityIdentity,
)

from ._ids import deterministic_id


class ResearchEntityValidationError(ValueError):
    """Invalid research identity validation input."""


def validate_research_entity(
    *,
    entity: ResearchEntityIdentity,
    result: RawResearchResult,
    known_entities: tuple[ResearchEntityIdentity, ...] = (),
) -> EntityValidationDecision:
    """Validate one search observation against supplied identity data only."""
    if not isinstance(entity, ResearchEntityIdentity):
        raise ResearchEntityValidationError("entity must be a ResearchEntityIdentity")
    if not isinstance(result, RawResearchResult):
        raise ResearchEntityValidationError("result must be a RawResearchResult")
    if not isinstance(known_entities, tuple) or any(
        not isinstance(item, ResearchEntityIdentity) for item in known_entities
    ):
        raise ResearchEntityValidationError(
            "known_entities must be a tuple of ResearchEntityIdentity"
        )
    if result.entity_type is not entity.entity_type:
        raise ResearchEntityValidationError("research result entity_type does not match target")
    if len({item.entity_id for item in known_entities}) != len(known_entities):
        raise ResearchEntityValidationError("known_entities contains duplicate IDs")
    if any(item.entity_id == entity.entity_id for item in known_entities):
        raise ResearchEntityValidationError("known_entities must not include the target entity")

    text = f"{result.title}\n{result.content}"
    normalized_text = _normalize_text(text)
    target_name_match = _contains_phrase(normalized_text, entity.name)
    alias_match = any(_contains_phrase(normalized_text, alias) for alias in entity.aliases)
    similar_name = _has_partial_name_overlap(normalized_text, entity.name)
    target_url_match = _url_matches_result(entity.linkedin_url, result)
    mismatched_entity_url = _has_different_linkedin_entity_url(
        entity.linkedin_url,
        result,
    )

    other_name_matches = tuple(
        known
        for known in known_entities
        if known.entity_type is entity.entity_type and _contains_phrase(normalized_text, known.name)
    )
    other_url_matches = tuple(
        known
        for known in known_entities
        if known.entity_type is entity.entity_type
        and _url_matches_result(known.linkedin_url, result)
    )
    other_matches = {item.entity_id: item for item in (*other_name_matches, *other_url_matches)}
    target_matches = target_name_match or alias_match or target_url_match
    conflict = bool(other_matches) or mismatched_entity_url

    matched_signals: list[IdentitySignal] = []
    if target_name_match:
        matched_signals.append(IdentitySignal.TARGET_NAME)
    if alias_match:
        matched_signals.append(IdentitySignal.EXPLICIT_ALIAS)
    if target_url_match:
        matched_signals.append(IdentitySignal.LINKEDIN_URL)

    conflicting_signals: list[IdentitySignal] = []
    if similar_name and not target_name_match and not alias_match:
        conflicting_signals.append(IdentitySignal.SIMILAR_NAME)
    if other_matches:
        conflicting_signals.append(IdentitySignal.OTHER_KNOWN_ENTITY)
    if mismatched_entity_url:
        conflicting_signals.append(IdentitySignal.CONFLICTING_LINKEDIN_URL)
    conflicting_entity_ids = tuple(sorted(other_matches))

    if target_matches and (
        conflict or (similar_name and not target_name_match and not alias_match)
    ):
        status = EntityValidationStatus.AMBIGUOUS
        reason = EntityValidationReason.CONFLICTING_IDENTITY_SIGNALS
    elif target_matches:
        status = EntityValidationStatus.VALIDATED
        if target_url_match:
            reason = EntityValidationReason.EXACT_LINKEDIN_URL_MATCH
        elif alias_match:
            reason = EntityValidationReason.EXPLICIT_ALIAS_MATCH
        else:
            reason = EntityValidationReason.EXACT_NAME_MATCH
    elif other_matches and not similar_name:
        status = EntityValidationStatus.REJECTED
        reason = EntityValidationReason.DIFFERENT_KNOWN_ENTITY
    elif similar_name:
        status = EntityValidationStatus.AMBIGUOUS
        reason = EntityValidationReason.SIMILAR_NAME_ONLY
    else:
        status = EntityValidationStatus.AMBIGUOUS
        reason = EntityValidationReason.INSUFFICIENT_IDENTITY

    provenance_refs = tuple(dict.fromkeys((*entity.provenance_refs, *result.provenance_refs)))
    decision_id = deterministic_id(
        "entity-validation",
        entity.entity_id,
        result.result_id,
        status.value,
        reason.value,
        *[signal.value for signal in matched_signals],
        *[signal.value for signal in conflicting_signals],
        *conflicting_entity_ids,
    )
    return EntityValidationDecision(
        decision_id=f"entity-validation-{decision_id}",
        entity_id=entity.entity_id,
        result_id=result.result_id,
        status=status,
        reason=reason,
        matched_signals=tuple(matched_signals),
        conflicting_signals=tuple(conflicting_signals),
        conflicting_entity_ids=conflicting_entity_ids,
        provenance_refs=provenance_refs,
    )


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", normalized, flags=re.UNICODE))


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_text(phrase)
    if not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {text} "


def _has_partial_name_overlap(text: str, name: str) -> bool:
    name_tokens = set(_normalize_text(name).split())
    if not name_tokens:
        return False
    text_tokens = set(text.split())
    return bool(name_tokens & text_tokens)


def _url_matches_result(
    target_url: str | None,
    result: RawResearchResult,
) -> bool:
    if target_url is None:
        return False
    normalized_target = _normalize_linkedin_url(target_url)
    result_urls = [result.url]
    result_urls.extend(re.findall(r"https?://[^\s<>\"')]+", result.title + " " + result.content))
    return any(
        _normalize_linkedin_url(candidate) == normalized_target
        for candidate in result_urls
        if _is_linkedin_url(candidate)
    )


def _is_linkedin_url(value: str) -> bool:
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return False
    return (parts.hostname or "").casefold() in {
        "linkedin.com",
        "www.linkedin.com",
    }


def _has_different_linkedin_entity_url(
    target_url: str | None,
    result: RawResearchResult,
) -> bool:
    if target_url is None:
        return False
    target = _normalize_linkedin_url(target_url)
    result_urls = [result.url]
    result_urls.extend(re.findall(r"https?://[^\s<>\"')]+", result.title + " " + result.content))
    for candidate in result_urls:
        if not _is_linkedin_url(candidate):
            continue
        parts = urlsplit(candidate.strip())
        path = parts.path.casefold().rstrip("/")
        if not (path.startswith("/company/") or path.startswith("/school/")):
            continue
        if _normalize_linkedin_url(candidate) != target:
            return True
    return False


def _normalize_linkedin_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        if parts.scheme.casefold() not in {"http", "https"} or not parts.hostname:
            raise ValueError
        host = parts.hostname.casefold()
        port = parts.port
    except ValueError as exc:
        raise ResearchEntityValidationError(
            f"invalid LinkedIn URL in research identity: {value!r}"
        ) from exc
    if host not in {"linkedin.com", "www.linkedin.com"}:
        raise ResearchEntityValidationError(
            f"identity URL is not a supported LinkedIn URL: {value!r}"
        )
    if port is not None:
        host = f"{host}:{port}"
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.casefold(), host, path, parts.query, parts.fragment))
