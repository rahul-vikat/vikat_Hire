from __future__ import annotations

import json
from datetime import date

import pytest

from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    ExtractionKind,
    NormalizedSourceState,
)
from vikat_hire.contracts.scope import ScopeEvidenceCategory
from vikat_hire.normalization.external import normalize_external_sources


def _block(
    text: str,
    *,
    source_type: SourceType = SourceType.LINKEDIN,
    source_ref: str = "linkedin-001",
    block_id: str = "external-block-001",
) -> ExtractedTextBlock:
    return ExtractedTextBlock(
        block_id=block_id,
        source_type=source_type,
        source_ref=source_ref,
        text=text,
        page_number=None,
        section="Profile",
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=(f"{source_ref}:source",),
    )


def test_empty_external_input_produces_no_invented_facts() -> None:
    result = normalize_external_sources(
        blocks=(),
        screening_id="screening-001",
    )

    assert result.claims == ()
    assert result.skills == ()
    assert result.responsibilities == ()
    assert result.experience_records == ()
    assert result.scope_evidence == ()
    assert result.source_states == {}


def test_linkedin_uses_conservative_explicit_skill_parsing() -> None:
    result = normalize_external_sources(
        blocks=(
            _block(
                "Skills: Python, PostgreSQL, FastAPI",
            ),
        ),
        screening_id="screening-001",
        source_states={
            "linkedin-001": NormalizedSourceState.AVAILABLE,
        },
    )

    assert [skill.name for skill in result.skills] == [
        "Python",
        "PostgreSQL",
        "FastAPI",
    ]

    assert result.skills[0].source_type is SourceType.LINKEDIN


def test_linkedin_apify_dataset_experience_flows_into_normalization() -> None:
    block = _block(
        json.dumps(
            [
                {
                    "experience": [
                        {
                            "position": "Engineer",
                            "companyName": "Example",
                            "skills": ["Python", "FastAPI"],
                            "startDate": {"month": 1, "year": 2020},
                            "endDate": {"month": 12, "year": 2022},
                            "description": "Built backend services.",
                        }
                    ]
                }
            ]
        ),
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-structured",
        block_id="linkedin-structured-block",
    )

    result = normalize_external_sources(
        blocks=(block,),
        screening_id="screening-001",
        source_states={
            "linkedin-structured": NormalizedSourceState.AVAILABLE,
        },
    )

    assert len(result.experience_records) == 1
    record = result.experience_records[0]
    assert record.role == "Engineer"
    assert record.employer == "Example"
    assert record.source_type is SourceType.LINKEDIN
    assert record.source_ref == "linkedin-structured"
    assert len(record.skill_refs) == 2
    assert len(record.responsibility_refs) == 1
    assert record.evidence_refs == ("linkedin-structured-block",)
    assert record.provenance_refs == ("linkedin-structured:source",)
    assert [item.name for item in result.skills] == ["Python", "FastAPI"]
    assert result.skills[0].evidence_refs == ("linkedin-structured-block",)
    assert result.skills[0].provenance_refs == ("linkedin-structured:source",)
    assert result.responsibilities[0].text == "Built backend services."


def test_github_scope_evidence_is_factual_only() -> None:
    result = normalize_external_sources(
        blocks=(
            _block(
                "Owned the authentication service end-to-end.",
                source_type=SourceType.GITHUB,
                source_ref="github-001",
            ),
        ),
        screening_id="screening-001",
        source_states={
            "github-001": NormalizedSourceState.AVAILABLE,
        },
    )

    assert len(result.scope_evidence) == 1
    assert (
        ScopeEvidenceCategory.OWNERSHIP
        in result.scope_evidence[0].scope_evidence.categories
    )
    assert not hasattr(result.scope_evidence[0].scope_evidence, "level")
    assert not hasattr(result.scope_evidence[0].scope_evidence, "score")


def test_portfolio_experience_preserves_factual_dates() -> None:
    result = normalize_external_sources(
        blocks=(
            _block(
                "Software Engineer at Acme — 2022-01 - 2024-06",
                source_type=SourceType.PORTFOLIO,
                source_ref="portfolio-001",
            ),
        ),
        screening_id="screening-001",
        source_states={
            "portfolio-001": NormalizedSourceState.AVAILABLE,
        },
    )

    assert len(result.experience_records) == 1

    record = result.experience_records[0]

    assert record.role == "Software Engineer"
    assert record.employer == "Acme"
    assert record.start_date == date(2022, 1, 1)
    assert record.end_date == date(2024, 6, 1)


def test_ambiguous_external_statement_is_left_unnormalized() -> None:
    result = normalize_external_sources(
        blocks=(
            _block(
                "Worked with many modern technologies over the years.",
            ),
        ),
        screening_id="screening-001",
    )

    assert result.experience_records == ()
    assert result.skills == ()
    assert result.scope_evidence == ()


def test_missing_external_source_remains_explicit() -> None:
    result = normalize_external_sources(
        blocks=(),
        screening_id="screening-001",
        source_states={
            "linkedin-001": NormalizedSourceState.NOT_FOUND,
            "github-001": NormalizedSourceState.NOT_AUTHORIZED,
            "portfolio-001": NormalizedSourceState.UNAVAILABLE,
            "portfolio-002": NormalizedSourceState.NOT_APPLICABLE,
        },
    )

    assert result.source_states == {
        "linkedin-001": NormalizedSourceState.NOT_FOUND,
        "github-001": NormalizedSourceState.NOT_AUTHORIZED,
        "portfolio-001": NormalizedSourceState.UNAVAILABLE,
        "portfolio-002": NormalizedSourceState.NOT_APPLICABLE,
    }


def test_same_fact_from_linkedin_and_github_is_not_deduplicated() -> None:
    result = normalize_external_sources(
        blocks=(
            _block(
                "Skills: Python",
                source_type=SourceType.LINKEDIN,
                source_ref="linkedin-001",
                block_id="linkedin-block",
            ),
            _block(
                "Skills: Python",
                source_type=SourceType.GITHUB,
                source_ref="github-001",
                block_id="github-block",
            ),
        ),
        screening_id="screening-001",
    )

    assert len(result.skills) == 2
    assert result.skills[0].source_type is SourceType.LINKEDIN
    assert result.skills[1].source_type is SourceType.GITHUB


def test_external_normalization_rejects_resume_blocks() -> None:
    with pytest.raises(ValueError, match="only accepts LinkedIn"):
        normalize_external_sources(
            blocks=(
                _block(
                    "Skills: Python",
                    source_type=SourceType.RESUME_FILE,
                    source_ref="resume-001",
                ),
            ),
            screening_id="screening-001",
        )


def test_available_source_requires_extracted_blocks() -> None:
    with pytest.raises(ValueError, match="must have extracted blocks"):
        normalize_external_sources(
            blocks=(),
            screening_id="screening-001",
            source_states={
                "linkedin-001": NormalizedSourceState.AVAILABLE,
            },
        )


def test_non_available_source_cannot_have_extracted_blocks() -> None:
    with pytest.raises(
        ValueError,
        match="cannot have extracted blocks",
    ):
        normalize_external_sources(
            blocks=(
                _block(
                    "Skills: Python",
                    source_type=SourceType.LINKEDIN,
                    source_ref="linkedin-001",
                ),
            ),
            screening_id="screening-001",
            source_states={
                "linkedin-001": NormalizedSourceState.NOT_AUTHORIZED,
            },
        )


def test_duplicate_block_ids_fail() -> None:
    block = _block("Skills: Python")

    with pytest.raises(ValueError, match="duplicate extracted block id"):
        normalize_external_sources(
            blocks=(block, block),
            screening_id="screening-001",
        )


def test_blank_screening_id_fails() -> None:
    with pytest.raises(ValueError, match="screening_id"):
        normalize_external_sources(
            blocks=(),
            screening_id="   ",
        )


def test_provenance_is_preserved_and_deduplicated_without_losing_source_refs() -> None:
    result = normalize_external_sources(
        blocks=(
            _block(
                "Skills: Python",
                source_type=SourceType.LINKEDIN,
                source_ref="linkedin-001",
                block_id="linkedin-block",
            ),
            _block(
                "Mentored two engineers.",
                source_type=SourceType.GITHUB,
                source_ref="github-001",
                block_id="github-block",
            ),
        ),
        screening_id="screening-001",
    )

    assert result.provenance_refs == (
        "linkedin-001:source",
        "github-001:source",
    )

    assert result.skills[0].source_ref == "linkedin-001"
    assert result.responsibilities[0].source_ref == "github-001"
