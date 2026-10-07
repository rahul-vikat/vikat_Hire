from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Iterable

from vikat_hire.contracts.common import (
    DatePrecision,
    EvidenceConfidence,
    EvidenceStatus,
    SourceType,
)
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.evaluation import ExperienceRecord
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    NormalizedClaim,
    NormalizedExperienceRecord,
    NormalizedResponsibility,
    NormalizedScopeEvidence,
    NormalizedSkill,
)
from vikat_hire.contracts.scope import ScopeEvidence, ScopeEvidenceCategory


_DATE_PATTERNS: tuple[tuple[re.Pattern[str], DatePrecision], ...] = (
    (
        re.compile(
            r"^(?P<month>\d{1,2})/(?P<year>\d{4})$"
        ),
        DatePrecision.MONTH,
    ),
    (
        re.compile(
            r"^(?P<year>\d{4})-(?P<month>\d{1,2})$"
        ),
        DatePrecision.MONTH,
    ),
    (
        re.compile(
            r"^(?P<year>\d{4})$"
        ),
        DatePrecision.YEAR,
    ),
)


def normalize_candidate(
    *,
    blocks: Iterable[ExtractedTextBlock],
    screening_id: str,
) -> tuple[
    tuple[NormalizedClaim, ...],
    tuple[NormalizedSkill, ...],
    tuple[NormalizedResponsibility, ...],
    tuple[NormalizedExperienceRecord, ...],
    tuple[NormalizedScopeEvidence, ...],
]:
    """
    Convert extracted candidate text into factual normalized observations.

    This function deliberately does not perform:
    - JD matching
    - semantic scoring
    - requirement satisfaction
    - seniority classification
    - suitability evaluation
    """

    if not screening_id.strip():
        raise ValueError("screening_id must not be blank")

    block_tuple = tuple(blocks)

    _validate_unique_block_ids(block_tuple)

    claims: list[NormalizedClaim] = []
    skills: list[NormalizedSkill] = []
    responsibilities: list[NormalizedResponsibility] = []
    experience_records: list[NormalizedExperienceRecord] = []
    scope_evidence: list[NormalizedScopeEvidence] = []

    for block in block_tuple:
        claims.extend(_extract_claims(block))
        skills.extend(_extract_skills(block))
        responsibilities.extend(_extract_responsibilities(block))
        experience_records.extend(_extract_experience_records(block))
        scope_evidence.extend(_extract_scope_evidence(block))

    return (
        tuple(claims),
        tuple(skills),
        tuple(responsibilities),
        tuple(experience_records),
        tuple(scope_evidence),
    )


def _validate_unique_block_ids(
    blocks: tuple[ExtractedTextBlock, ...],
) -> None:
    seen: set[str] = set()

    for block in blocks:
        if block.block_id in seen:
            raise ValueError(
                f"duplicate extracted block id: {block.block_id}"
            )
        seen.add(block.block_id)


def _extract_claims(
    block: ExtractedTextBlock,
) -> tuple[NormalizedClaim, ...]:
    """
    Create a factual claim from an explicit sentence.

    The current candidate normalizer intentionally uses conservative
    sentence-level claim extraction. It does not infer unstated facts.
    """
    sentences = _sentences(block.text)
    claims: list[NormalizedClaim] = []

    for index, sentence in enumerate(sentences):
        if not _looks_like_claim(sentence):
            continue

        claim_id = f"{block.block_id}:claim:{index}"

        claim = Claim(
            claim_id=claim_id,
            subject="candidate",
            predicate="candidate_statement",
            value=sentence,
            provenance_refs=block.provenance_refs,
        )

        claims.append(
            NormalizedClaim(
                claim=claim,
                source_type=block.source_type,
                source_ref=block.source_ref,
                evidence_status=EvidenceStatus.SUPPORTED,
                evidence_refs=(block.block_id,),
                provenance_refs=block.provenance_refs,
                confidence=EvidenceConfidence.MEDIUM,
            )
        )

    return tuple(claims)


def _extract_skills(
    block: ExtractedTextBlock,
) -> tuple[NormalizedSkill, ...]:
    """
    Extract explicitly listed skill observations.

    Only explicit skill-list patterns are normalized here.
    No JD comparison occurs.
    """
    lines = _nonempty_lines(block.text)
    results: list[NormalizedSkill] = []

    for line_index, line in enumerate(lines):
        skill_texts = _parse_skill_line(line)

        for skill_index, skill_text in enumerate(skill_texts):
            results.append(
                NormalizedSkill(
                    skill_id=(
                        f"{block.block_id}:skill:"
                        f"{line_index}:{skill_index}"
                    ),
                    name=skill_text,
                    canonical_ref=None,
                    source_type=block.source_type,
                    source_ref=block.source_ref,
                    evidence_status=EvidenceStatus.SUPPORTED,
                    evidence_refs=(block.block_id,),
                    provenance_refs=block.provenance_refs,
                    confidence=EvidenceConfidence.HIGH,
                )
            )

    return tuple(results)


def _extract_responsibilities(
    block: ExtractedTextBlock,
) -> tuple[NormalizedResponsibility, ...]:
    lines = _nonempty_lines(block.text)
    results: list[NormalizedResponsibility] = []

    for line_index, line in enumerate(lines):
        if not _looks_like_responsibility(line):
            continue

        results.append(
            NormalizedResponsibility(
                responsibility_id=(
                    f"{block.block_id}:responsibility:{line_index}"
                ),
                text=_strip_list_marker(line),
                source_type=block.source_type,
                source_ref=block.source_ref,
                evidence_status=EvidenceStatus.SUPPORTED,
                evidence_refs=(block.block_id,),
                provenance_refs=block.provenance_refs,
                confidence=EvidenceConfidence.MEDIUM,
            )
        )

    return tuple(results)


def _extract_experience_records(
    block: ExtractedTextBlock,
) -> tuple[NormalizedExperienceRecord, ...]:
    lines = _nonempty_lines(block.text)
    results: list[NormalizedExperienceRecord] = []

    for line_index, line in enumerate(lines):
        parsed = _parse_experience_line(line)

        if parsed is None:
            continue

        (
            employer,
            role,
            start_date,
            end_date,
            date_precision,
            current,
        ) = parsed

        results.append(
            NormalizedExperienceRecord(
                record_id=f"{block.block_id}:experience:{line_index}",
                employer=employer,
                role=role,
                start_date=start_date,
                end_date=end_date,
                date_precision=date_precision,
                current=current,
                skill_refs=(),
                responsibility_refs=(),
                source_text=line,
                source_type=block.source_type,
                source_ref=block.source_ref,
                evidence_refs=(block.block_id,),
                provenance_refs=block.provenance_refs,
            )
        )

    return tuple(results)


def _extract_scope_evidence(
    block: ExtractedTextBlock,
) -> tuple[NormalizedScopeEvidence, ...]:
    lines = _nonempty_lines(block.text)
    results: list[NormalizedScopeEvidence] = []

    for line_index, line in enumerate(lines):
        categories = _scope_categories(line)
        supervision_learning = _is_supervision_learning(line)

        if not categories and not supervision_learning:
            continue

        evidence = ScopeEvidence(
            evidence_id=f"{block.block_id}:scope:{line_index}",
            categories=tuple(categories),
            supervision_learning=supervision_learning,
            explicit_text=line,
            provenance_refs=block.provenance_refs,
        )

        results.append(
            NormalizedScopeEvidence(
                scope_evidence=evidence,
                source_type=block.source_type,
                source_ref=block.source_ref,
                evidence_refs=(block.block_id,),
                provenance_refs=block.provenance_refs,
            )
        )

    return tuple(results)


def _sentences(text: str) -> tuple[str, ...]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)

    return tuple(
        part.strip()
        for part in parts
        if part.strip()
    )


def _nonempty_lines(text: str) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in text.splitlines()
        if line.strip()
    )


def _looks_like_claim(text: str) -> bool:
    lowered = text.lower()

    return any(
        marker in lowered
        for marker in (
            "i ",
            "i'm ",
            "i am ",
            "worked ",
            "owned ",
            "built ",
            "developed ",
            "experienced ",
            "specialized ",
            "specialised ",
            "certified ",
        )
    )


def _parse_skill_line(line: str) -> tuple[str, ...]:
    lowered = line.lower()

    prefixes = (
        "skills:",
        "technical skills:",
        "technologies:",
        "technology:",
        "tools:",
        "languages:",
        "programming languages:",
    )

    prefix = next(
        (
            candidate
            for candidate in prefixes
            if lowered.startswith(candidate)
        ),
        None,
    )

    if prefix is None:
        return ()

    remainder = line[len(prefix):].strip()

    if not remainder:
        return ()

    return tuple(
        item.strip()
        for item in re.split(r"[,;|]", remainder)
        if item.strip()
    )


def _looks_like_responsibility(line: str) -> bool:
    text = _strip_list_marker(line).lower()

    return text.startswith(
        (
            "owned ",
            "led ",
            "built ",
            "developed ",
            "designed ",
            "implemented ",
            "managed ",
            "mentored ",
            "maintained ",
            "delivered ",
            "supported ",
            "operated ",
            "architected ",
            "defined ",
        )
    )


def _strip_list_marker(text: str) -> str:
    return re.sub(
        r"^\s*(?:[-*•]|\d+[.)])\s*",
        "",
        text,
    ).strip()


def _parse_experience_line(
    line: str,
) -> tuple[
    str | None,
    str | None,
    date | None,
    date | None,
    DatePrecision,
    bool,
] | None:
    """
    Parse conservative explicit employment/date patterns.

    Accepted examples:

        Software Engineer | Acme | 2022-01 - 2024-06
        Software Engineer — Acme — 2022 - 2024
        Software Engineer at Acme (2022-01 - Present)

    Anything ambiguous is left unnormalized rather than guessed.
    """
    match = re.search(
        r"(?P<start>\d{4}(?:-\d{1,2})?)"
        r"\s*(?:-|–|—|to)\s*"
        r"(?P<end>\d{4}(?:-\d{1,2})?|present|current)\b",
        line,
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    start, start_precision = _parse_date_token(match.group("start"))

    end_token = match.group("end").lower()

    if end_token in {"present", "current"}:
        end = None
        end_precision = start_precision
        current = True
    else:
        end, end_precision = _parse_date_token(end_token)
        current = False

    if start is None:
        return None

    date_precision = (
        DatePrecision.MONTH
        if (
            start_precision == DatePrecision.MONTH
            and end_precision == DatePrecision.MONTH
        )
        else DatePrecision.YEAR
    )

    prefix = line[: match.start()].strip(" -–—|:")

    employer: str | None = None
    role: str | None = None

    at_match = re.match(
        r"(?P<role>.+?)\s+at\s+(?P<employer>.+?)$",
        prefix,
        flags=re.IGNORECASE,
    )

    if at_match:
        role = at_match.group("role").strip()
        employer = at_match.group("employer").strip()
    elif "|" in prefix:
        parts = [part.strip() for part in prefix.split("|") if part.strip()]

        if len(parts) == 2:
            role, employer = parts
        elif len(parts) == 1:
            role = parts[0]
    elif prefix:
        role = prefix

    return (
        employer,
        role,
        start,
        end,
        date_precision,
        current,
    )


def _parse_date_token(
    token: str,
) -> tuple[date | None, DatePrecision]:
    token = token.strip()

    for pattern, precision in _DATE_PATTERNS:
        match = pattern.match(token)

        if match is None:
            continue

        year = int(match.group("year"))

        if precision == DatePrecision.YEAR:
            return date(year, 1, 1), precision

        month = int(match.group("month"))

        if not 1 <= month <= 12:
            raise ValueError(
                f"invalid month in date token: {token!r}"
            )

        return date(year, month, 1), precision

    raise ValueError(f"unsupported date token: {token!r}")


def _scope_categories(
    text: str,
) -> list[ScopeEvidenceCategory]:
    lowered = text.lower()

    categories: list[ScopeEvidenceCategory] = []

    if _contains_any(
        lowered,
        (
            "owned ",
            "ownership",
            "end-to-end",
            "end to end",
        ),
    ):
        categories.append(ScopeEvidenceCategory.OWNERSHIP)

    if _contains_any(
        lowered,
        (
            "technical decision",
            "design decision",
            "api design",
            "database design",
            "made architecture",
            "architecture decision",
        ),
    ):
        categories.append(
            ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY
        )

    if _contains_any(
        lowered,
        (
            "architecture",
            "architected",
            "architectural",
        ),
    ):
        categories.append(ScopeEvidenceCategory.ARCHITECTURE)

    if _contains_any(
        lowered,
        (
            "mentored ",
            "mentoring",
            "managed a team",
            "managed engineers",
            "people management",
            "team leadership",
        ),
    ):
        categories.append(ScopeEvidenceCategory.PEOPLE_LEADERSHIP)

    if _contains_any(
        lowered,
        (
            "cross-team",
            "cross team",
            "multiple teams",
            "across teams",
            "cross-functional",
        ),
    ):
        categories.append(ScopeEvidenceCategory.CROSS_TEAM_SCOPE)

    if _contains_any(
        lowered,
        (
            "production ownership",
            "production responsibility",
            "on-call",
            "operational ownership",
            "operated production",
            "production systems",
        ),
    ):
        categories.append(
            ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP
        )

    if _contains_any(
        lowered,
        (
            "engineering strategy",
            "technical strategy",
            "defined engineering direction",
            "engineering direction",
        ),
    ):
        categories.append(
            ScopeEvidenceCategory.ENGINEERING_STRATEGY
        )

    return _dedupe_categories(categories)


def _is_supervision_learning(text: str) -> bool:
    lowered = text.lower()

    return _contains_any(
        lowered,
        (
            "under supervision",
            "under direct supervision",
            "supervised work",
            "learning under",
            "trainee",
            "training role",
            "apprentice",
            "intern",
        ),
    )


def _contains_any(
    text: str,
    markers: tuple[str, ...],
) -> bool:
    return any(marker in text for marker in markers)


def _dedupe_categories(
    categories: Iterable[ScopeEvidenceCategory],
) -> list[ScopeEvidenceCategory]:
    seen: set[ScopeEvidenceCategory] = set()
    result: list[ScopeEvidenceCategory] = []

    for category in categories:
        if category in seen:
            continue

        seen.add(category)
        result.append(category)

    return result
