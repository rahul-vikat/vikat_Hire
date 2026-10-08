from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    DatePrecision,
    EvidenceConfidence,
    EvidenceStatus,
    RequirementImportance,
    SourceType,
)
from vikat_hire.contracts.evaluation import ExperienceRequirement
from vikat_hire.contracts.normalization import (
    NormalizedExperienceRecord,
    NormalizedResponsibility,
    NormalizedSkill,
)
from vikat_hire.evaluation.experience import evaluate_jd_aligned_experience
from vikat_hire.evaluation.experience_alignment import (
    ExperienceAlignmentError,
    match_experience_records,
)
from vikat_hire.evaluation.keyword_matcher import KeywordDefinition


def _requirement(
    requirement_id: str,
    text: str,
    *,
    canonical_skill_refs: tuple[str, ...] = (),
) -> ExperienceRequirement:
    return ExperienceRequirement(
        requirement_id=requirement_id,
        text=text,
        importance=RequirementImportance.MUST_HAVE,
        minimum_years=Decimal("3"),
        canonical_skill_refs=canonical_skill_refs,
        provenance_refs=(f"jd-prov-{requirement_id}",),
    )


def _record(
    record_id: str,
    *,
    role: str | None = None,
    skill_refs: tuple[str, ...] = (),
    responsibility_refs: tuple[str, ...] = (),
    evidence_refs: tuple[str, ...] | None = None,
) -> NormalizedExperienceRecord:
    return NormalizedExperienceRecord(
        record_id=record_id,
        employer=f"Employer {record_id}",
        role=role,
        start_date=date(2020, 1, 1),
        end_date=date(2022, 12, 31),
        date_precision=DatePrecision.MONTH,
        current=False,
        skill_refs=skill_refs,
        responsibility_refs=responsibility_refs,
        source_text=f"Source text for {record_id}",
        source_type=SourceType.LINKEDIN,
        source_ref=f"source-{record_id}",
        evidence_refs=evidence_refs or (f"evidence-{record_id}",),
        provenance_refs=(f"provenance-{record_id}",),
    )


def _skill(
    skill_id: str,
    name: str,
    *,
    canonical_ref: str | None = None,
) -> NormalizedSkill:
    return NormalizedSkill(
        skill_id=skill_id,
        name=name,
        canonical_ref=canonical_ref,
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-profile",
        evidence_status=EvidenceStatus.SUPPORTED,
        evidence_refs=(f"evidence-{skill_id}",),
        provenance_refs=(f"provenance-{skill_id}",),
        confidence=EvidenceConfidence.HIGH,
    )


def _responsibility(
    responsibility_id: str,
    text: str,
) -> NormalizedResponsibility:
    return NormalizedResponsibility(
        responsibility_id=responsibility_id,
        text=text,
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-profile",
        evidence_status=EvidenceStatus.SUPPORTED,
        evidence_refs=(f"evidence-{responsibility_id}",),
        provenance_refs=(f"provenance-{responsibility_id}",),
        confidence=EvidenceConfidence.MEDIUM,
    )


def test_responsibility_is_primary_explicit_match() -> None:
    req = _requirement("req-1", "payment APIs")
    resp = _responsibility("resp-1", "Build payment APIs for merchants.")

    result = match_experience_records(
        requirement=req,
        records=(_record("exp-1", responsibility_refs=("resp-1",)),),
        skills=(),
        responsibilities=(resp,),
    )

    assert result == frozenset({"exp-1"})


def test_explicit_skill_reference_supports_a_match() -> None:
    req = _requirement(
        "req-1",
        "experience building services",
        canonical_skill_refs=("skill:distributed-systems",),
    )
    skill = _skill(
        "skill-1",
        "distributed systems",
        canonical_ref="skill:distributed-systems",
    )

    assert match_experience_records(
        requirement=req,
        records=(_record("exp-1", skill_refs=("skill-1",)),),
        skills=(skill,),
        responsibilities=(),
    ) == frozenset({"exp-1"})


def test_description_derived_normalized_responsibility_matches() -> None:
    req = _requirement("req-1", "payment systems in production")
    resp = _responsibility(
        "desc-resp-1",
        "Operate payment systems in production for merchants.",
    )

    result = match_experience_records(
        requirement=req,
        records=(_record("exp-1", responsibility_refs=("desc-resp-1",)),),
        skills=(),
        responsibilities=(resp,),
    )

    assert result == frozenset({"exp-1"})


def test_title_similarity_alone_never_matches() -> None:
    req = _requirement("req-1", "build payment APIs")

    result = match_experience_records(
        requirement=req,
        records=(_record("exp-1", role="Payment API Engineer"),),
        skills=(),
        responsibilities=(),
    )

    assert result == frozenset()


def test_multiple_records_are_matched_independently() -> None:
    req = _requirement("req-1", "payment APIs")
    responsibilities = (
        _responsibility("resp-1", "Build payment APIs for merchant systems."),
        _responsibility("resp-2", "Build payment APIs for internal teams."),
    )
    records = (
        _record("exp-1", responsibility_refs=("resp-1",)),
        _record("exp-2", responsibility_refs=("resp-2",)),
    )

    assert match_experience_records(
        requirement=req,
        records=records,
        skills=(),
        responsibilities=responsibilities,
    ) == frozenset({"exp-1", "exp-2"})


def test_one_record_can_match_multiple_requirements() -> None:
    record = _record("exp-1", responsibility_refs=("resp-1",))
    responsibilities = (
        _responsibility("resp-1", "Build payment APIs for merchants."),
    )

    results = tuple(
        match_experience_records(
            requirement=_requirement(req_id, "payment APIs"),
            records=(record,),
            skills=(),
            responsibilities=responsibilities,
        )
        for req_id in ("req-a", "req-b")
    )

    assert results == (frozenset({"exp-1"}), frozenset({"exp-1"}))


def test_empty_records_or_evidence_produce_no_match() -> None:
    req = _requirement("req-1", "build payment APIs")

    assert match_experience_records(
        requirement=req,
        records=(),
        skills=(),
        responsibilities=(),
    ) == frozenset()
    assert match_experience_records(
        requirement=req,
        records=(_record("exp-1"),),
        skills=(),
        responsibilities=(),
    ) == frozenset()


def test_duplicate_observation_ids_are_rejected() -> None:
    req = _requirement("req-1", "build payment APIs")
    with pytest.raises(ExperienceAlignmentError, match="duplicate responsibility IDs"):
        match_experience_records(
            requirement=req,
            records=(_record("exp-1", responsibility_refs=("resp-1",)),),
            skills=(),
            responsibilities=(
                _responsibility("resp-1", "Built payment APIs."),
                _responsibility("resp-1", "Built payment APIs."),
            ),
        )


def test_record_with_duplicate_evidence_refs_is_reported_once() -> None:
    req = _requirement("req-1", "payment APIs")
    resp = _responsibility("resp-1", "Build payment APIs for merchants.")
    record = _record(
        "exp-1",
        responsibility_refs=("resp-1",),
        evidence_refs=("same-evidence", "same-evidence"),
    )

    assert match_experience_records(
        requirement=req,
        records=(record,),
        skills=(),
        responsibilities=(resp,),
    ) == frozenset({"exp-1"})


def test_matched_record_audit_refs_survive_missing_dates() -> None:
    req = _requirement("req-1", "payment APIs")
    resp = _responsibility("resp-1", "Build payment APIs for merchants.")
    record = _record(
        "exp-1",
        responsibility_refs=("resp-1",),
    ).model_copy(update={"start_date": None, "end_date": None})
    matched = match_experience_records(
        requirement=req,
        records=(record,),
        skills=(),
        responsibilities=(resp,),
    )

    result = evaluate_jd_aligned_experience(
        records=(record.to_evaluation_record(),),
        requirement=req,
        matched_record_ids=matched,
        as_of_date=date(2026, 10, 8),
    )

    assert result.raw_value == Decimal("0.00")
    assert result.evidence_refs == ("evidence-exp-1",)
    assert result.provenance_refs == (
        "jd-prov-req-1",
        "provenance-exp-1",
    )


def test_unlinked_evidence_reference_fails_loudly() -> None:
    with pytest.raises(ExperienceAlignmentError, match="unknown responsibilities"):
        match_experience_records(
            requirement=_requirement("req-1", "build payment APIs"),
            records=(_record("exp-1", responsibility_refs=("missing",)),),
            skills=(),
            responsibilities=(),
        )


def test_requirement_vocabulary_is_used_deterministically() -> None:
    req = _requirement("req-1", "agentic AI orchestration")
    vocabulary = KeywordDefinition(
        canonical_ref="agentic-ai",
        keywords=("multi-agent workflows",),
    )
    resp = _responsibility("resp-1", "Built multi-agent workflows across products.")

    kwargs = {
        "requirement": req,
        "records": (_record("exp-1", responsibility_refs=("resp-1",)),),
        "skills": (),
        "responsibilities": (resp,),
        "vocabulary": vocabulary,
    }
    assert match_experience_records(**kwargs) == match_experience_records(**kwargs)
    assert match_experience_records(**kwargs) == frozenset({"exp-1"})
