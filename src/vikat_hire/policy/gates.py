from __future__ import annotations

from collections.abc import Iterable

from vikat_hire.contracts.common import RequirementCategory
from vikat_hire.contracts.normalization import (
    JDRequirement,
    NormalizationResult,
    NormalizedEducationRecord,
)
from vikat_hire.contracts.policy import GateResult, GateStatus

GATE_CERTIFICATION = "certification"
GATE_EDUCATION = "education"
GATE_LOCATION = "location"
GATE_AVAILABILITY = "availability"
MANDATORY_GATES = (
    GATE_CERTIFICATION,
    GATE_EDUCATION,
    GATE_LOCATION,
    GATE_AVAILABILITY,
)

_CATEGORY_BY_GATE = {
    GATE_CERTIFICATION: RequirementCategory.CERTIFICATION,
    GATE_EDUCATION: RequirementCategory.EDUCATION,
    GATE_LOCATION: RequirementCategory.LOCATION,
    GATE_AVAILABILITY: RequirementCategory.AVAILABILITY,
}


def evaluate_mandatory_gates(
    *,
    normalization: NormalizationResult,
    configuration_ref: str,
) -> tuple[GateResult, ...]:
    """Evaluate policy gates from this screening's normalized artifacts.

    Matching rules for education, certification, location, and availability
    are not yet approved. Consequently, no applicable requirement can pass:
    it fails conservatively until an approved deterministic matcher exists.
    """
    if not isinstance(normalization, NormalizationResult):
        raise TypeError("normalization must be a NormalizationResult")
    if not configuration_ref.strip():
        raise ValueError("configuration_ref must not be blank")

    _validate_normalization(normalization)

    results: list[GateResult] = []
    for name in MANDATORY_GATES:
        category = _CATEGORY_BY_GATE[name]
        requirements = tuple(
            item for item in normalization.jd_requirements if item.category is category
        )
        requirement_refs = tuple(item.requirement_id for item in requirements)
        evidence_refs = (
            _candidate_evidence_refs(
                name=name,
                education_records=normalization.education_records,
            )
            if requirements
            else ()
        )

        if not requirements:
            status = GateStatus.NOT_APPLICABLE
            rationale = f"No normalized JD {name} requirement applies."
        else:
            status = GateStatus.FAIL
            rationale = _failure_rationale(name=name)

        results.append(
            GateResult(
                name=name,
                status=status,
                requirement_refs=requirement_refs,
                evidence_refs=evidence_refs,
                rationale=rationale,
                configuration_ref=configuration_ref,
            )
        )
    return tuple(results)


def _candidate_evidence_refs(
    *,
    name: str,
    education_records: Iterable[NormalizedEducationRecord],
) -> tuple[str, ...]:
    if name != GATE_EDUCATION:
        # No typed candidate observation exists for the other gate categories.
        return ()
    return tuple(dict.fromkeys(ref for record in education_records for ref in record.evidence_refs))


def _failure_rationale(*, name: str) -> str:
    if name == GATE_EDUCATION:
        return (
            "Education requirement is applicable, but the education matching "
            "rule is not approved; satisfaction was not established."
        )
    if name == GATE_CERTIFICATION:
        return (
            "Certification requirement is applicable, but no approved typed "
            "certification evidence and matching rule established satisfaction."
        )
    if name == GATE_LOCATION:
        return (
            "Location requirement is applicable, but no approved structured "
            "location/work-mode evidence and comparison rule established satisfaction."
        )
    return (
        "Availability requirement is applicable, but no approved explicit "
        "availability evidence and matching rule established satisfaction."
    )


def _validate_normalization(normalization: NormalizationResult) -> None:
    requirements = normalization.jd_requirements
    requirement_ids = [item.requirement_id for item in requirements]
    if len(requirement_ids) != len(set(requirement_ids)):
        raise ValueError("normalization contains duplicate JD requirement IDs")
    for item in requirements:
        if not isinstance(item, JDRequirement):
            raise TypeError("jd_requirements must contain JDRequirement objects")
