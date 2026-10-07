from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from vikat_hire.contracts.common import (
    RequirementCategory,
    RequirementImportance,
    ScopeEvidenceCategory,
)
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    JDExperienceRequirement,
    JDRequirement,
    NormalizedJDScopeEvidence,
)
from vikat_hire.contracts.scope import ScopeEvidencePolarity


_REQUIREMENT_PREFIXES: tuple[tuple[str, RequirementCategory], ...] = (
    ("must have:", RequirementCategory.MUST_HAVE),
    ("must-have:", RequirementCategory.MUST_HAVE),
    ("required:", RequirementCategory.MUST_HAVE),
    ("requirements:", RequirementCategory.MUST_HAVE),
    ("nice to have:", RequirementCategory.NICE_TO_HAVE),
    ("nice-to-have:", RequirementCategory.NICE_TO_HAVE),
    ("preferred:", RequirementCategory.NICE_TO_HAVE),
    ("bonus:", RequirementCategory.NICE_TO_HAVE),
)


_EXPERIENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:at least|minimum(?: of)?|minimum)\s+"
        r"(?P<years>\d+(?:\.\d+)?)\s*(?:\+?\s*)years?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<years>\d+(?:\.\d+)?)\s*\+?\s*years?\s+"
        r"(?:of\s+)?experience\b",
        re.IGNORECASE,
    ),
)


_SCOPE_MARKERS: tuple[
    tuple[ScopeEvidenceCategory, tuple[str, ...]],
] = (
    (
        ScopeEvidenceCategory.OWNERSHIP,
        (
            "own end-to-end",
            "owned end-to-end",
            "owning end-to-end",
            "end-to-end ownership",
            "own features",
            "own services",
            "own systems",
            "ownership",
        ),
    ),
    (
        ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
        (
            "technical decision",
            "technical decisions",
            "design decisions",
            "made architecture decisions",
            "api design decisions",
            "database design decisions",
            "technical authority",
        ),
    ),
    (
        ScopeEvidenceCategory.ARCHITECTURE,
        (
            "architecture",
            "architectural",
            "architected",
            "system design",
            "architecture decisions",
        ),
    ),
    (
        ScopeEvidenceCategory.PEOPLE_LEADERSHIP,
        (
            "mentor engineers",
            "mentoring engineers",
            "mentor developers",
            "manage engineers",
            "managed engineers",
            "manage a team",
            "managed a team",
            "team leadership",
            "people leadership",
        ),
    ),
    (
        ScopeEvidenceCategory.CROSS_TEAM_SCOPE,
        (
            "cross-team",
            "cross team",
            "multiple teams",
            "across teams",
            "cross-functional",
            "cross functional",
        ),
    ),
    (
        ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
        (
            "production ownership",
            "production responsibility",
            "production systems",
            "on-call",
            "on call",
            "operational ownership",
            "operate production",
            "operated production",
        ),
    ),
    (
        ScopeEvidenceCategory.ENGINEERING_STRATEGY,
        (
            "engineering strategy",
            "technical strategy",
            "engineering direction",
            "technical direction",
            "define engineering strategy",
            "defined engineering strategy",
        ),
    ),
)


_SUPERVISION_MARKERS: tuple[str, ...] = (
    "under supervision",
    "direct supervision",
    "supervised work",
    "learning under",
    "trainee",
    "training role",
    "apprentice",
    "intern",
)


def normalize_jd(
    *,
    blocks: tuple[ExtractedTextBlock, ...] | list[ExtractedTextBlock],
    screening_id: str,
) -> tuple[
    tuple[JDRequirement, ...],
    tuple[JDExperienceRequirement, ...],
    tuple[NormalizedJDScopeEvidence, ...],
]:
    """Normalize explicit JD requirements without evaluating a candidate."""

    if not screening_id.strip():
        raise ValueError("screening_id must not be blank")

    block_tuple = tuple(blocks)

    block_ids = [block.block_id for block in block_tuple]
    if len(block_ids) != len(set(block_ids)):
        raise ValueError("duplicate extracted block IDs are not allowed")

    requirements: list[JDRequirement] = []
    experience_requirements: list[JDExperienceRequirement] = []
    scope_evidence: list[NormalizedJDScopeEvidence] = []

    for block in block_tuple:
        for line_number, raw_line in enumerate(
            block.text.splitlines(),
            start=1,
        ):
            line = _clean_line(raw_line)
            if not line:
                continue

            requirement = _parse_requirement(
                line=line,
                block=block,
                line_number=line_number,
            )
            if requirement is not None:
                requirements.append(requirement)

                experience_requirement = _parse_experience_requirement(
                    line=line,
                    requirement=requirement,
                    block=block,
                )
                if experience_requirement is not None:
                    experience_requirements.append(experience_requirement)

            jd_scope = _parse_scope_evidence(
                line=line,
                block=block,
            )
            if jd_scope is not None:
                scope_evidence.append(jd_scope)

    return (
        tuple(requirements),
        tuple(experience_requirements),
        tuple(scope_evidence),
    )


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _strip_bullet(value: str) -> str:
    return re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", value).strip()


def _parse_requirement(
    *,
    line: str,
    block: ExtractedTextBlock,
    line_number: int,
) -> JDRequirement | None:
    normalized = _strip_bullet(line)
    lowered = normalized.casefold()

    category: RequirementCategory | None = None
    requirement_text = normalized

    for prefix, candidate_category in _REQUIREMENT_PREFIXES:
        if lowered.startswith(prefix):
            category = candidate_category
            requirement_text = normalized[len(prefix):].strip()
            break

    if category is None:
        if _looks_like_requirement(normalized):
            category = _infer_requirement_category(normalized)

    if category is None or not requirement_text:
        return None

    importance = _importance_for_category(category)

    evidence_ref = f"{block.block_id}:line:{line_number}"

    return JDRequirement(
        requirement_id=evidence_ref,
        category=category,
        importance=importance,
        text=requirement_text,
        canonical_refs=(),
        source_type=block.source_type,
        source_ref=block.block_id,
        evidence_refs=(evidence_ref,),
        provenance_refs=block.provenance_refs,
    )


def _looks_like_requirement(line: str) -> bool:
    lowered = line.casefold()

    markers = (
        "required",
        "must ",
        "should ",
        "experience with",
        "experience in",
        "proficiency in",
        "proficient in",
        "knowledge of",
        "familiarity with",
        "ability to",
        "responsible for",
        "responsibilities:",
        "qualifications:",
        "skills:",
    )

    return lowered.startswith(markers)


def _infer_requirement_category(line: str) -> RequirementCategory:
    lowered = line.casefold()

    if any(
        marker in lowered
        for marker in (
            "nice to have",
            "nice-to-have",
            "preferred",
            "bonus",
        )
    ):
        return RequirementCategory.NICE_TO_HAVE

    return RequirementCategory.MUST_HAVE


def _importance_for_category(
    category: RequirementCategory,
) -> RequirementImportance:
    if category is RequirementCategory.NICE_TO_HAVE:
        return RequirementImportance.NICE_TO_HAVE

    return RequirementImportance.MUST_HAVE


def _parse_experience_requirement(
    *,
    line: str,
    requirement: JDRequirement,
    block: ExtractedTextBlock,
) -> JDExperienceRequirement | None:
    match = None

    for pattern in _EXPERIENCE_PATTERNS:
        match = pattern.search(line)
        if match is not None:
            break

    if match is None:
        return None

    years_text = match.group("years")

    try:
        minimum_years = Decimal(years_text)
    except InvalidOperation as exc:
        raise ValueError(
            f"invalid minimum experience value: {years_text!r}"
        ) from exc

    if minimum_years <= Decimal("0"):
        raise ValueError("minimum_years must be greater than zero")

    return JDExperienceRequirement(
        requirement_id=requirement.requirement_id,
        text=requirement.text,
        importance=requirement.importance,
        minimum_years=minimum_years,
        canonical_skill_refs=requirement.canonical_refs,
        provenance_refs=block.provenance_refs,
    )


def _parse_scope_evidence(
    *,
    line: str,
    block: ExtractedTextBlock,
) -> NormalizedJDScopeEvidence | None:
    normalized = _strip_bullet(line)
    lowered = normalized.casefold()

    categories: list[ScopeEvidenceCategory] = []

    for category, markers in _SCOPE_MARKERS:
        if any(marker in lowered for marker in markers):
            categories.append(category)

    supervision_learning = any(
        marker in lowered
        for marker in _SUPERVISION_MARKERS
    )

    if not categories and not supervision_learning:
        return None

    polarity = _scope_polarity(lowered)

    evidence_id = f"{block.block_id}:scope"

    return NormalizedJDScopeEvidence(
        evidence_id=evidence_id,
        categories=tuple(categories),
        supervision_learning=supervision_learning,
        polarity=polarity,
        explicit_text=normalized,
        provenance_refs=block.provenance_refs,
    )


def _scope_polarity(line: str) -> ScopeEvidencePolarity:
    contradicting_markers = (
        "without",
        "no responsibility",
        "not responsible",
        "does not own",
        "doesn't own",
        "no ownership",
        "under supervision",
    )

    if any(marker in line for marker in contradicting_markers):
        return ScopeEvidencePolarity.CONTRADICTING

    return ScopeEvidencePolarity.SUPPORTING