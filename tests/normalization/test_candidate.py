from __future__ import annotations

from datetime import date

import pytest

from vikat_hire.contracts.common import (
    InputKind,
    SourceType,
)
from vikat_hire.contracts.inputs import DocumentInput
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    ExtractionKind,
)
from vikat_hire.contracts.scope import ScopeEvidenceCategory
from vikat_hire.normalization.candidate import normalize_candidate


def _block(
    text: str,
    *,
    block_id: str = "block-001",
) -> ExtractedTextBlock:
    return ExtractedTextBlock(
        block_id=block_id,
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-001",
        text=text,
        page_number=1,
        section="Experience",
        extraction_kind=ExtractionKind.PDF_TEXT,
        provenance_refs=("resume-001:page:1",),
    )


def test_empty_candidate_blocks_produce_no_invented_facts() -> None:
    result = normalize_candidate(
        blocks=(),
        screening_id="screening-001",
    )

    claims, skills, responsibilities, experiences, scope = result

    assert claims == ()
    assert skills == ()
    assert responsibilities == ()
    assert experiences == ()
    assert scope == ()


def test_skill_list_becomes_skill_observation() -> None:
    result = normalize_candidate(
        blocks=(
            _block(
                "Technical Skills: Python, PostgreSQL, FastAPI",
            ),
        ),
        screening_id="screening-001",
    )

    _, skills, _, _, _ = result

    assert [skill.name for skill in skills] == [
        "Python",
        "PostgreSQL",
        "FastAPI",
    ]

    assert all(skill.canonical_ref is None for skill in skills)


def test_skill_normalization_does_not_create_match() -> None:
    result = normalize_candidate(
        blocks=(_block("Skills: Python"),),
        screening_id="screening-001",
    )

    _, skills, _, _, _ = result

    assert len(skills) == 1
    assert not hasattr(skills[0], "score")
    assert not hasattr(skills[0], "match_status")


def test_responsibility_is_preserved_as_observation() -> None:
    result = normalize_candidate(
        blocks=(
            _block(
                "- Owned the authentication service end-to-end.\n"
                "- Mentored two engineers."
            ),
        ),
        screening_id="screening-001",
    )

    _, _, responsibilities, _, _ = result

    assert [item.text for item in responsibilities] == [
        "Owned the authentication service end-to-end.",
        "Mentored two engineers.",
    ]


def test_scope_evidence_normalizes_explicit_categories_only() -> None:
    result = normalize_candidate(
        blocks=(
            _block(
                "Owned the authentication service end-to-end.\n"
                "Mentored two engineers."
            ),
        ),
        screening_id="screening-001",
    )

    _, _, _, _, scope = result

    assert len(scope) == 2

    assert (
        ScopeEvidenceCategory.OWNERSHIP
        in scope[0].scope_evidence.categories
    )

    assert (
        ScopeEvidenceCategory.PEOPLE_LEADERSHIP
        in scope[1].scope_evidence.categories
    )

    assert not hasattr(scope[0].scope_evidence, "level")
    assert not hasattr(scope[0].scope_evidence, "score")


def test_scope_normalization_does_not_assign_seniority() -> None:
    result = normalize_candidate(
        blocks=(
            _block(
                "Led a cross-team migration and made architecture decisions."
            ),
        ),
        screening_id="screening-001",
    )

    _, _, _, _, scope = result

    assert len(scope) == 1
    assert (
        ScopeEvidenceCategory.CROSS_TEAM_SCOPE
        in scope[0].scope_evidence.categories
    )
    assert (
        ScopeEvidenceCategory.ARCHITECTURE
        in scope[0].scope_evidence.categories
    )

    assert not hasattr(scope[0], "candidate_level")
    assert not hasattr(scope[0], "seniority_score")


def test_experience_record_is_factual_only() -> None:
    result = normalize_candidate(
        blocks=(
            _block(
                "Software Engineer at Acme — 2022-01 - 2024-06",
            ),
        ),
        screening_id="screening-001",
    )

    _, _, _, experiences, _ = result

    assert len(experiences) == 1

    experience = experiences[0]

    assert experience.role == "Software Engineer"
    assert experience.employer == "Acme"
    assert experience.start_date == date(2022, 1, 1)
    assert experience.end_date == date(2024, 6, 1)
    assert experience.date_precision.value == "month"

    assert not hasattr(experience, "score")
    assert not hasattr(experience, "aligned_years")
    assert not hasattr(experience, "requirement_match")


def test_current_experience_has_no_end_date() -> None:
    result = normalize_candidate(
        blocks=(
            _block(
                "Senior Engineer at Acme — 2022 - Present",
            ),
        ),
        screening_id="screening-001",
    )

    _, _, _, experiences, _ = result

    assert len(experiences) == 1
    assert experiences[0].current is True
    assert experiences[0].end_date is None


def test_ambiguous_experience_text_is_not_guessed() -> None:
    result = normalize_candidate(
        blocks=(
            _block(
                "Worked at Acme for several years.",
            ),
        ),
        screening_id="screening-001",
    )

    _, _, _, experiences, _ = result

    assert experiences == ()


def test_invalid_month_fails_loudly() -> None:
    with pytest.raises(ValueError, match="invalid month"):
        normalize_candidate(
            blocks=(
                _block(
                    "Engineer at Acme — 2024-13 - 2025-01",
                ),
            ),
            screening_id="screening-001",
        )


def test_claim_preserves_original_statement_and_provenance() -> None:
    result = normalize_candidate(
        blocks=(
            _block(
                "I worked on distributed systems.",
            ),
        ),
        screening_id="screening-001",
    )

    claims, _, _, _, _ = result

    assert len(claims) == 1

    normalized_claim = claims[0]

    assert normalized_claim.claim.value == (
        "I worked on distributed systems."
    )
    assert normalized_claim.evidence_refs == ("block-001",)
    assert normalized_claim.provenance_refs == (
        "resume-001:page:1",
    )


def test_same_fact_from_two_sources_is_not_silently_deduplicated() -> None:
    first = _block(
        "Skills: Python",
        block_id="resume-block",
    )

    second = ExtractedTextBlock(
        block_id="linkedin-block",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-001",
        text="Skills: Python",
        page_number=None,
        section="Skills",
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=("linkedin-001",),
    )

    _, skills, _, _, _ = normalize_candidate(
        blocks=(first, second),
        screening_id="screening-001",
    )

    assert len(skills) == 2
    assert skills[0].source_type == SourceType.RESUME_FILE
    assert skills[1].source_type == SourceType.LINKEDIN


def test_duplicate_block_ids_fail() -> None:
    block = _block("Skills: Python")

    with pytest.raises(ValueError, match="duplicate extracted block id"):
        normalize_candidate(
            blocks=(block, block),
            screening_id="screening-001",
        )


def test_blank_screening_id_fails() -> None:
    with pytest.raises(ValueError, match="screening_id"):
        normalize_candidate(
            blocks=(),
            screening_id="   ",
        )