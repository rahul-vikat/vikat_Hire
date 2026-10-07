"""Pure classification from explicit JD skills/responsibilities and configured rules."""

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from vikat_hire.config.jd_classification import JDClassificationConfiguration, normalize_indicator
from vikat_hire.contracts.common import RequirementCategory, ReviewReason, SourceType
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.contracts.policy import ReviewRequest
from vikat_hire.contracts.state import ClassificationResult


@dataclass(frozen=True)
class JDClassificationAssessment:
    classification: ClassificationResult | None
    review: ReviewRequest | None


def classify_jd_requirements(
    *,
    requirements: tuple[JDRequirement, ...],
    configuration: JDClassificationConfiguration,
    created_at: datetime,
) -> JDClassificationAssessment:
    """Exact whole-requirement matching after case/whitespace normalization.

    Only SKILL and RESPONSIBILITY requirements can select a class. Education,
    titles, employer details, compensation, and candidate artifacts are not used.
    Unknown evidence never defaults to non-technical. Both classes require review.
    The caller supplies the timestamp so replay does not create new timestamps.
    """
    if not isinstance(configuration, JDClassificationConfiguration):
        raise ValueError("configuration must be a JDClassificationConfiguration")
    configuration = JDClassificationConfiguration.model_validate(configuration.model_dump())
    checked: list[JDRequirement] = []
    for requirement in requirements:
        if not isinstance(requirement, JDRequirement):
            raise ValueError("requirements must contain JDRequirement objects")
        requirement = JDRequirement.model_validate(requirement.model_dump())
        if requirement.source_type is not SourceType.JD_FILE:
            raise ValueError("classification requires JD evidence only")
        if any(
            not ref.strip()
            for ref in (
                requirement.requirement_id,
                requirement.source_ref,
                *requirement.evidence_refs,
                *requirement.provenance_refs,
            )
        ):
            raise ValueError("JD requirement references must not be blank")
        checked.append(requirement)
    ordered = sorted(checked, key=lambda item: item.requirement_id)
    if len({item.requirement_id for item in ordered}) != len(ordered):
        raise ValueError("duplicate JD requirement IDs")
    eligible = [
        item
        for item in ordered
        if item.category
        in {
            RequirementCategory.SKILL,
            RequirementCategory.RESPONSIBILITY,
        }
    ]
    matches = {
        label: [item for item in eligible if normalize_indicator(item.text) in indicators]
        for label, indicators in (
            ("technical", configuration.technical_indicators),
            ("non_technical", configuration.non_technical_indicators),
        )
    }
    labels = [label for label, items in matches.items() if items]
    if len(labels) == 1:
        label = labels[0]
        matched = matches[label]
        return JDClassificationAssessment(
            ClassificationResult(
                jd_type=label,
                rationale=(
                    f"Exact JD requirement indicators matched {label}; "
                    f"configuration={configuration.configuration_ref}; requirements="
                    + ", ".join(item.requirement_id for item in matched)
                ),
                provenance_refs=tuple(
                    sorted({ref for item in matched for ref in item.provenance_refs})
                ),
                created_at=created_at,
            ),
            None,
        )
    reason = ReviewReason.CONTRADICTION if len(labels) == 2 else ReviewReason.AMBIGUOUS_REQUIREMENT
    detail = (
        "Conflicting classification indicators"
        if len(labels) == 2
        else "No classification indicator matched"
    )
    refs = tuple(sorted({ref for item in ordered for ref in item.evidence_refs}))
    provenance = tuple(sorted({ref for item in ordered for ref in item.provenance_refs}))
    action = (
        f"{detail}; review JD classification before external-evidence routing. "
        f"configuration={configuration.configuration_ref}; provenance={','.join(provenance)}"
    )
    fingerprint = json.dumps(
        [configuration.model_dump(), [item.model_dump(mode="json") for item in ordered]],
        sort_keys=True,
    )
    return JDClassificationAssessment(
        None,
        ReviewRequest(
            review_id="jd-classification-" + sha256(fingerprint.encode()).hexdigest(),
            reason=reason,
            blocking=True,
            evidence_refs=refs,
            requested_action=action,
            created_at=created_at,
        ),
    )
