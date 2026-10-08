from __future__ import annotations

from vikat_hire.contracts.common import EvidenceStatus
from vikat_hire.contracts.evaluation import ExperienceRequirement
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.normalization import (
    NormalizedExperienceRecord,
    NormalizedResponsibility,
    NormalizedSkill,
)
from vikat_hire.evaluation.keyword_matcher import (
    KeywordDefinition,
    KeywordMatchingError,
    RequirementKeyword,
    match_requirement,
)


class ExperienceAlignmentError(ValueError):
    """Raised when normalized experience evidence cannot be aligned safely."""


def match_experience_records(
    *,
    requirement: ExperienceRequirement,
    records: tuple[NormalizedExperienceRecord, ...],
    skills: tuple[NormalizedSkill, ...],
    responsibilities: tuple[NormalizedResponsibility, ...],
    vocabulary: KeywordDefinition | None = None,
) -> frozenset[str]:
    """Return record IDs supported by linked, explicit normalized evidence.

    The existing deterministic keyword matcher is applied only to the
    requirement-linked responsibility and skill observations. Role titles and
    duration are deliberately not matching inputs. Explicit canonical skill
    references are accepted as direct supporting evidence.
    """
    if not isinstance(requirement, ExperienceRequirement):
        raise ExperienceAlignmentError("requirement must be an ExperienceRequirement")
    if not isinstance(records, tuple) or any(
        not isinstance(record, NormalizedExperienceRecord) for record in records
    ):
        raise ExperienceAlignmentError(
            "records must be a tuple of NormalizedExperienceRecord objects"
        )
    if not isinstance(skills, tuple) or any(
        not isinstance(skill, NormalizedSkill) for skill in skills
    ):
        raise ExperienceAlignmentError(
            "skills must be a tuple of NormalizedSkill objects"
        )
    if not isinstance(responsibilities, tuple) or any(
        not isinstance(item, NormalizedResponsibility)
        for item in responsibilities
    ):
        raise ExperienceAlignmentError(
            "responsibilities must be a tuple of NormalizedResponsibility objects"
        )
    if vocabulary is not None and not isinstance(vocabulary, KeywordDefinition):
        raise ExperienceAlignmentError("vocabulary must be a KeywordDefinition or None")

    _ensure_unique_ids(records, "experience record", lambda item: item.record_id)
    _ensure_unique_ids(skills, "skill", lambda item: item.skill_id)
    _ensure_unique_ids(
        responsibilities,
        "responsibility",
        lambda item: item.responsibility_id,
    )

    skill_by_id = {skill.skill_id: skill for skill in skills}
    responsibility_by_id = {
        item.responsibility_id: item for item in responsibilities
    }
    requirement_keyword = RequirementKeyword(
        requirement_id=requirement.requirement_id,
        text=requirement.text,
        vocabulary=vocabulary,
    )
    matched: set[str] = set()

    for record in records:
        _ensure_unique_refs(record.skill_refs, "skill", record.record_id)
        _ensure_unique_refs(
            record.responsibility_refs,
            "responsibility",
            record.record_id,
        )
        unknown_skills = set(record.skill_refs) - skill_by_id.keys()
        if unknown_skills:
            raise ExperienceAlignmentError(
                f"experience record {record.record_id!r} references unknown skills: "
                f"{sorted(unknown_skills)}"
            )
        unknown_responsibilities = (
            set(record.responsibility_refs) - responsibility_by_id.keys()
        )
        if unknown_responsibilities:
            raise ExperienceAlignmentError(
                f"experience record {record.record_id!r} references unknown responsibilities: "
                f"{sorted(unknown_responsibilities)}"
            )

        linked_responsibilities = tuple(
            responsibility_by_id[ref]
            for ref in record.responsibility_refs
        )
        if any(
            item.evidence_status in {
                EvidenceStatus.SUPPORTED,
                EvidenceStatus.PARTIALLY_SUPPORTED,
            }
            and _matches(
                requirement_keyword,
                Claim(
                    claim_id=item.responsibility_id,
                    subject="candidate",
                    predicate="normalized_responsibility",
                    value=item.text,
                    provenance_refs=item.provenance_refs,
                ),
            )
            for item in linked_responsibilities
        ):
            matched.add(record.record_id)
            continue

        linked_skills = tuple(skill_by_id[ref] for ref in record.skill_refs)
        if any(
            skill.evidence_status in {
                EvidenceStatus.SUPPORTED,
                EvidenceStatus.PARTIALLY_SUPPORTED,
            }
            and _skill_matches(
                skill=skill,
                requirement=requirement,
                requirement_keyword=requirement_keyword,
            )
            for skill in linked_skills
        ):
            matched.add(record.record_id)

    return frozenset(matched)


def _matches(requirement: RequirementKeyword, claim: Claim) -> bool:
    try:
        return bool(match_requirement(requirement=requirement, claims=(claim,)))
    except KeywordMatchingError as exc:
        raise ExperienceAlignmentError(str(exc)) from exc


def _skill_matches(*, skill: NormalizedSkill, requirement: ExperienceRequirement,
                   requirement_keyword: RequirementKeyword) -> bool:
    if (
        skill.canonical_ref is not None
        and skill.canonical_ref
        in {
            *requirement.canonical_skill_refs,
            *(
                (requirement_keyword.vocabulary.canonical_ref,)
                if requirement_keyword.vocabulary is not None
                else ()
            ),
        }
    ):
        return True
    return _matches(
        requirement_keyword,
        Claim(
            claim_id=skill.skill_id,
            subject="candidate",
            predicate="normalized_skill",
            value=skill.name,
            provenance_refs=skill.provenance_refs,
        ),
    )


def _ensure_unique_ids(items, label: str, id_getter) -> None:
    identifiers = [id_getter(item) for item in items]
    if any(not isinstance(identifier, str) or not identifier.strip() for identifier in identifiers):
        raise ExperienceAlignmentError(f"{label} IDs must be non-blank strings")
    if len(identifiers) != len(set(identifiers)):
        raise ExperienceAlignmentError(f"duplicate {label} IDs are not allowed")


def _ensure_unique_refs(refs: tuple[str, ...], label: str, record_id: str) -> None:
    if len(refs) != len(set(refs)):
        raise ExperienceAlignmentError(
            f"experience record {record_id!r} contains duplicate {label} references"
        )
