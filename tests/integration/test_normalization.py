from __future__ import annotations

from vikat_hire.contracts.common import (
    SourceType,
)
from vikat_hire.contracts.inputs import DocumentInput
from vikat_hire.contracts.normalization import (
    ExtractionKind,
    ExtractedTextBlock,
    NormalizedSourceState,
)
from vikat_hire.contracts.scope import (
    ScopeEvidenceCategory,
    ScopeEvidencePolarity,
)
from vikat_hire.normalization.candidate import normalize_candidate
from vikat_hire.normalization.document import extract_document_text
from vikat_hire.normalization.external import normalize_external_sources
from vikat_hire.normalization.jd import normalize_jd


def _document(
    *,
    input_id: str,
    kind: str,
    filename: str,
) -> DocumentInput:
    return DocumentInput(
        input_id=input_id,
        kind=kind,
        filename=filename,
        media_type="text/plain",
        content_hash=f"hash-{input_id}",
        storage_ref=f"storage://{input_id}",
    )


def _external_block(
    *,
    block_id: str,
    source_type: SourceType,
    source_ref: str,
    text: str,
    provenance: str,
) -> ExtractedTextBlock:
    return ExtractedTextBlock(
        block_id=block_id,
        source_type=source_type,
        source_ref=source_ref,
        text=text,
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=(provenance,),
    )


def test_resume_document_extraction_flows_into_candidate_normalization() -> None:
    document = _document(
        input_id="resume-001",
        kind="resume",
        filename="resume.txt",
    )

    blocks = extract_document_text(
        document=document,
        content=(
            b"Skills: Python, PostgreSQL\n"
            b"Software Engineer at Acme -- 2022-01 - 2024-06\n"
            b"Owned the authentication service end-to-end."
        ),
        provenance_refs=("resume-001:source",),
    )

    claims, skills, responsibilities, experiences, scope = (
        normalize_candidate(
            blocks=blocks,
            screening_id="screening-001",
        )
    )

    assert len(blocks) == 1
    assert blocks[0].source_type is SourceType.RESUME_FILE
    assert blocks[0].source_ref == "resume-001"
    assert blocks[0].provenance_refs == ("resume-001:source",)

    assert [skill.name for skill in skills] == [
        "Python",
        "PostgreSQL",
    ]

    assert len(experiences) == 1
    assert experiences[0].employer == "Acme"

    assert len(scope) == 1
    assert (
        ScopeEvidenceCategory.OWNERSHIP
        in scope[0].scope_evidence.categories
    )

    assert claims
    assert responsibilities == ()

    for item in (*claims, *skills, *experiences, *scope):
        assert item.provenance_refs == ("resume-001:source",)

    assert not hasattr(scope[0].scope_evidence, "level")
    assert not hasattr(scope[0].scope_evidence, "score")


def test_jd_document_extraction_flows_into_jd_normalization() -> None:
    document = _document(
        input_id="jd-001",
        kind="jd",
        filename="job-description.txt",
    )

    blocks = extract_document_text(
        document=document,
        content=(
            b"Must have: Python and PostgreSQL\n"
            b"Must have: at least 5 years of Python experience\n"
            b"Own production services and make architecture decisions.\n"
            b"No responsibility for production ownership."
        ),
        provenance_refs=("jd-001:source",),
    )

    requirements, experience_requirements, scope = normalize_jd(
        blocks=blocks,
        screening_id="screening-001",
    )

    assert len(blocks) == 1
    assert blocks[0].source_type is SourceType.JD_FILE
    assert blocks[0].source_ref == "jd-001"

    assert len(requirements) == 2
    assert len(experience_requirements) == 1
    assert experience_requirements[0].minimum_years == 5

    assert len(scope) == 2

    assert scope[0].polarity is ScopeEvidencePolarity.SUPPORTING
    assert (
        ScopeEvidenceCategory.OWNERSHIP
        in scope[0].categories
    )
    assert (
        ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY
        in scope[0].categories
    )

    assert scope[1].polarity is ScopeEvidencePolarity.CONTRADICTING
    assert (
        ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP
        in scope[1].categories
    )

    for requirement in requirements:
        assert requirement.provenance_refs == ("jd-001:source",)

    for evidence in scope:
        assert evidence.provenance_refs == ("jd-001:source",)
        assert not hasattr(evidence, "required_level")
        assert not hasattr(evidence, "score")


def test_external_normalization_integrates_with_extracted_external_evidence() -> None:
    linkedin_block = _external_block(
        block_id="linkedin-block-001",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-001",
        text="Skills: Python, PostgreSQL",
        provenance="linkedin-001:source",
    )

    github_block = _external_block(
        block_id="github-block-001",
        source_type=SourceType.GITHUB,
        source_ref="github-001",
        text="Owned the authentication service end-to-end.",
        provenance="github-001:source",
    )

    result = normalize_external_sources(
        blocks=(linkedin_block, github_block),
        screening_id="screening-001",
        source_states={
            "linkedin-001": NormalizedSourceState.AVAILABLE,
            "github-001": NormalizedSourceState.AVAILABLE,
        },
    )

    assert result.screening_id == "screening-001"

    assert result.source_states == {
        "linkedin-001": NormalizedSourceState.AVAILABLE,
        "github-001": NormalizedSourceState.AVAILABLE,
    }

    assert [skill.name for skill in result.skills] == [
        "Python",
        "PostgreSQL",
    ]

    assert len(result.scope_evidence) == 1
    assert (
        ScopeEvidenceCategory.OWNERSHIP
        in result.scope_evidence[0].scope_evidence.categories
    )

    assert result.provenance_refs == (
        "linkedin-001:source",
        "github-001:source",
    )


def test_same_fact_across_resume_and_external_source_retains_provenance() -> None:
    resume_block = ExtractedTextBlock(
        block_id="resume-block-001",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-001",
        text="Skills: Python",
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=("resume-001:source",),
    )

    linkedin_block = _external_block(
        block_id="linkedin-block-001",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-001",
        text="Skills: Python",
        provenance="linkedin-001:source",
    )

    _, resume_skills, _, _, _ = normalize_candidate(
        blocks=(resume_block,),
        screening_id="screening-001",
    )

    external_result = normalize_external_sources(
        blocks=(linkedin_block,),
        screening_id="screening-001",
        source_states={
            "linkedin-001": NormalizedSourceState.AVAILABLE,
        },
    )

    assert len(resume_skills) == 1
    assert len(external_result.skills) == 1

    assert resume_skills[0].name == "Python"
    assert external_result.skills[0].name == "Python"

    assert resume_skills[0].source_ref == "resume-001"
    assert external_result.skills[0].source_ref == "linkedin-001"

    assert resume_skills[0].provenance_refs == (
        "resume-001:source",
    )
    assert external_result.skills[0].provenance_refs == (
        "linkedin-001:source",
    )


def test_external_missing_state_survives_normalization_without_invented_evidence() -> None:
    result = normalize_external_sources(
        blocks=(),
        screening_id="screening-001",
        source_states={
            "linkedin-001": NormalizedSourceState.NOT_FOUND,
            "github-001": NormalizedSourceState.NOT_AUTHORIZED,
            "portfolio-001": NormalizedSourceState.UNAVAILABLE,
        },
    )

    assert result.source_states == {
        "linkedin-001": NormalizedSourceState.NOT_FOUND,
        "github-001": NormalizedSourceState.NOT_AUTHORIZED,
        "portfolio-001": NormalizedSourceState.UNAVAILABLE,
    }

    assert result.claims == ()
    assert result.skills == ()
    assert result.responsibilities == ()
    assert result.experience_records == ()
    assert result.scope_evidence == ()
    assert result.provenance_refs == ()


def test_normalization_preserves_jd_scope_contradiction_for_downstream_evaluation() -> None:
    document = _document(
        input_id="jd-002",
        kind="jd",
        filename="contradictory-jd.txt",
    )

    blocks = extract_document_text(
        document=document,
        content=(
            b"Own production services.\n"
            b"No responsibility for production ownership."
        ),
        provenance_refs=("jd-002:source",),
    )

    _, _, scope = normalize_jd(
        blocks=blocks,
        screening_id="screening-002",
    )

    assert len(scope) == 2

    polarities = [evidence.polarity for evidence in scope]

    assert ScopeEvidencePolarity.SUPPORTING in polarities
    assert ScopeEvidencePolarity.CONTRADICTING in polarities

    assert all(
        evidence.explicit_text
        for evidence in scope
    )

    assert all(
        evidence.provenance_refs == ("jd-002:source",)
        for evidence in scope
    )


def test_normalization_outputs_do_not_contain_evaluation_or_scoring_results() -> None:
    resume_document = _document(
        input_id="resume-002",
        kind="resume",
        filename="resume.txt",
    )

    resume_blocks = extract_document_text(
        document=resume_document,
        content=b"Skills: Python\nOwned services end-to-end.",
        provenance_refs=("resume-002:source",),
    )

    claims, skills, responsibilities, experiences, scope = (
        normalize_candidate(
            blocks=resume_blocks,
            screening_id="screening-003",
        )
    )

    for collection in (
        claims,
        skills,
        responsibilities,
        experiences,
        scope,
    ):
        for item in collection:
            dumped = item.model_dump()
            assert "score" not in dumped
            assert "raw_score" not in dumped
            assert "match" not in dumped
            assert "suitability" not in dumped
            assert "eligible" not in dumped
            assert "required_level" not in dumped

    jd_blocks = extract_document_text(
        document=_document(
            input_id="jd-002",
            kind="jd",
            filename="jd.txt",
        ),
        content=b"Must have: Python",
        provenance_refs=("jd-002:source",),
    )

    requirements, experience_requirements, jd_scope = normalize_jd(
        blocks=jd_blocks,
        screening_id="screening-003",
    )

    for collection in (
        requirements,
        experience_requirements,
        jd_scope,
    ):
        for item in collection:
            dumped = item.model_dump()
            assert "score" not in dumped
            assert "raw_score" not in dumped
            assert "match" not in dumped
            assert "suitability" not in dumped
            assert "eligible" not in dumped
            assert "required_level" not in dumped


def test_same_extracted_resume_input_produces_same_normalized_structure() -> None:
    document = _document(
        input_id="resume-deterministic",
        kind="resume",
        filename="resume.txt",
    )

    content = (
        b"Skills: Python, FastAPI\n"
        b"Software Engineer at Acme -- 2021-01 - 2024-01\n"
        b"Owned services end-to-end."
    )

    first_blocks = extract_document_text(
        document=document,
        content=content,
        provenance_refs=("resume-deterministic:source",),
    )

    second_blocks = extract_document_text(
        document=document,
        content=content,
        provenance_refs=("resume-deterministic:source",),
    )

    assert first_blocks == second_blocks

    first = normalize_candidate(
        blocks=first_blocks,
        screening_id="screening-deterministic",
    )
    second = normalize_candidate(
        blocks=second_blocks,
        screening_id="screening-deterministic",
    )

    assert first == second