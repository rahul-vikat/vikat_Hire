from __future__ import annotations

import pytest
from pydantic import ValidationError

from vikat_hire.contracts.research import (
    EntityValidationReason,
    EntityValidationStatus,
    IdentitySignal,
    ResearchDimension,
    ResearchEntityIdentity,
    ResearchEntityType,
)
from vikat_hire.research.entities import build_research_entities
from vikat_hire.research.validation import (
    ResearchEntityValidationError,
    validate_research_entity,
)


def test_normalized_exact_entity_name_validates(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        title="Vikat—AI announces funding",
        content="Investors support VIKAT.AI.",
    )

    decision = validate_research_entity(entity=company_entity, result=result)

    assert decision.status is EntityValidationStatus.VALIDATED
    assert decision.reason is EntityValidationReason.EXACT_NAME_MATCH
    assert IdentitySignal.TARGET_NAME in decision.matched_signals
    assert decision.provenance_refs == (
        "linkedin-provenance-1",
        "searx-provenance-result-1",
    )


def test_explicit_alias_validates_but_unconfigured_alias_does_not(
    company_entity,
    research_result_factory,
) -> None:
    with_alias = company_entity.model_copy(update={"aliases": ("VikatAI",)})
    result = research_result_factory(
        title="VikatAI funding update",
        content="Investors back this organization.",
    )

    validated = validate_research_entity(entity=with_alias, result=result)
    not_inferred = validate_research_entity(entity=company_entity, result=result)

    assert validated.status is EntityValidationStatus.VALIDATED
    assert validated.reason is EntityValidationReason.EXPLICIT_ALIAS_MATCH
    assert not_inferred.status is EntityValidationStatus.AMBIGUOUS


def test_exact_full_linkedin_url_validates_without_host_only_match(
    company_entity,
    research_result_factory,
) -> None:
    exact = research_result_factory(
        title="Company information",
        url="https://www.linkedin.com/company/vikat-ai/",
        content="",
    )
    shared_host_only = research_result_factory(
        title="Unrelated company",
        url="https://www.linkedin.com/company/other-company/",
        content="",
    )

    assert (
        validate_research_entity(entity=company_entity, result=exact).status
        is EntityValidationStatus.VALIDATED
    )
    assert (
        validate_research_entity(
            entity=company_entity,
            result=shared_host_only,
        ).status
        is EntityValidationStatus.AMBIGUOUS
    )


def test_target_name_conflicts_with_another_linkedin_entity_url(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        title="VIKAT.AI company information",
        url="https://www.linkedin.com/company/other-company/",
    )

    decision = validate_research_entity(entity=company_entity, result=result)

    assert decision.status is EntityValidationStatus.AMBIGUOUS
    assert decision.reason is EntityValidationReason.CONFLICTING_IDENTITY_SIGNALS
    assert IdentitySignal.CONFLICTING_LINKEDIN_URL in decision.conflicting_signals


def test_conflicting_known_entity_is_ambiguous(
    company_entity,
    research_result_factory,
) -> None:
    other = company_entity.model_copy(
        update={
            "entity_id": "company-other",
            "name": "Other Company",
            "provider_id": "company-456",
            "linkedin_url": "https://www.linkedin.com/company/other-company/",
        }
    )
    result = research_result_factory(
        title="VIKAT.AI and Other Company market report",
        content="Both companies are discussed.",
    )

    decision = validate_research_entity(
        entity=company_entity,
        result=result,
        known_entities=(other,),
    )

    assert decision.status is EntityValidationStatus.AMBIGUOUS
    assert decision.reason is EntityValidationReason.CONFLICTING_IDENTITY_SIGNALS
    assert IdentitySignal.TARGET_NAME in decision.matched_signals
    assert IdentitySignal.OTHER_KNOWN_ENTITY in decision.conflicting_signals


def test_clearly_different_known_entity_is_rejected(
    company_entity,
    research_result_factory,
) -> None:
    other = company_entity.model_copy(
        update={"entity_id": "company-other", "name": "Other Company"}
    )
    result = research_result_factory(
        title="Other Company valuation",
        content="Investors discussed a separate company.",
    )

    decision = validate_research_entity(
        entity=company_entity,
        result=result,
        known_entities=(other,),
    )

    assert decision.status is EntityValidationStatus.REJECTED
    assert decision.reason is EntityValidationReason.DIFFERENT_KNOWN_ENTITY


def test_similar_but_non_equivalent_name_is_ambiguous(
    college_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        entity_type=ResearchEntityType.COLLEGE,
        title="Patna Institute announces a new campus",
        content="New infrastructure is planned.",
    )

    decision = validate_research_entity(entity=college_entity, result=result)

    assert decision.status is EntityValidationStatus.AMBIGUOUS


def test_no_identity_signal_is_ambiguous(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        title="Industry overview",
        content="A general discussion of investment and revenue.",
    )

    decision = validate_research_entity(entity=company_entity, result=result)

    assert decision.status is EntityValidationStatus.AMBIGUOUS
    assert decision.reason is EntityValidationReason.INSUFFICIENT_IDENTITY


def test_invalid_target_url_fails_loudly(
    company_entity,
    research_result_factory,
) -> None:
    invalid_entity = company_entity.model_copy(update={"linkedin_url": "not-a-linkedin-url"})

    with pytest.raises(ResearchEntityValidationError, match="invalid LinkedIn URL"):
        validate_research_entity(
            entity=invalid_entity,
            result=research_result_factory(),
        )


def test_blank_identity_name_is_rejected_by_contract(company_entity) -> None:
    values = company_entity.model_dump()
    values["name"] = ""
    with pytest.raises(ValidationError, match="at least 1 character"):
        ResearchEntityIdentity(**values)


def test_identity_validation_is_deterministic(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory()

    first = validate_research_entity(entity=company_entity, result=result)
    second = validate_research_entity(entity=company_entity, result=result)

    assert first == second


def test_raw_result_contract_rejects_entity_dimension_mismatch(
    company_entity,
    research_result_factory,
) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="dimension does not match"):
        research_result_factory(
            entity_type=ResearchEntityType.COLLEGE,
            dimension=ResearchDimension.FINANCIAL_VALUATION,
        )


def test_entity_targets_come_from_normalized_records() -> None:
    from vikat_hire.contracts.common import SourceType
    from vikat_hire.contracts.normalization import (
        NormalizedEducationRecord,
        NormalizedExperienceRecord,
    )

    experience = NormalizedExperienceRecord(
        record_id="exp-1",
        employer="Company A",
        company_id="id-a",
        company_universal_name="company-a",
        company_linkedin_url="https://www.linkedin.com/company/company-a/",
        source_text="Work details",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-1",
        evidence_refs=("block-1",),
        provenance_refs=("prov-1",),
    )
    education = NormalizedEducationRecord(
        education_id="edu-1",
        school_name="College A",
        school_id="school-a",
        school_linkedin_url="https://www.linkedin.com/company/college-a/",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-1",
        evidence_refs=("block-1",),
        provenance_refs=("prov-1",),
    )

    entities = build_research_entities(
        experience_records=(experience,),
        education_records=(education,),
    )

    assert [(item.entity_type, item.name) for item in entities] == [
        (ResearchEntityType.COMPANY, "Company A"),
        (ResearchEntityType.COLLEGE, "College A"),
    ]
    assert entities[0].universal_name == "company-a"
    assert entities[0].provider_id == "id-a"
    assert entities[1].provider_id == "school-a"
