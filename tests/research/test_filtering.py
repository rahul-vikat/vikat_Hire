from __future__ import annotations

import pytest

from vikat_hire.config.research_relevance import (
    COLLEGE_RELEVANCE_TERMS,
    COMPANY_RELEVANCE_TERMS,
)
from vikat_hire.contracts.research import (
    DimensionRelevanceReason,
    DimensionRelevanceStatus,
    EntityValidationStatus,
    ResearchDimension,
    ResearchEntityType,
    ResearchFilterReason,
    ResearchFilterStatus,
)
from vikat_hire.research.filtering import (
    ResearchEvidenceFilteringError,
    filter_research_evidence,
)
from vikat_hire.research.validation import validate_research_entity


def _assessment(entity, result):
    validation = validate_research_entity(entity=entity, result=result)
    return filter_research_evidence(
        entity=entity,
        result=result,
        validation=validation,
    )


def test_relevance_vocabulary_is_explicit_and_covers_all_dimensions() -> None:
    assert COMPANY_RELEVANCE_TERMS == {
        ResearchDimension.FINANCIAL_VALUATION: (
            "financial",
            "funding",
            "valuation",
            "revenue",
            "investors",
            "investment",
        ),
        ResearchDimension.MARKET_POSITION: (
            "market",
            "position",
            "customers",
            "products",
            "competitors",
        ),
        ResearchDimension.ENGINEERING_TECHNICAL: (
            "engineering",
            "technical",
            "technology",
            "AI",
            "patents",
            "research",
        ),
        ResearchDimension.REPUTATION_COMPLIANCE: (
            "reputation",
            "certifications",
            "compliance",
            "security",
        ),
    }
    assert COLLEGE_RELEVANCE_TERMS == {
        ResearchDimension.OFFICIAL_RANKING: (
            "official",
            "ranking",
            "NIRF",
            "QS",
            "THE ranking",
        ),
        ResearchDimension.ACCREDITATION: (
            "accreditation",
            "NAAC",
            "NBA",
            "UGC",
            "AICTE",
            "recognition",
        ),
        ResearchDimension.ACADEMIC_RESEARCH: (
            "academic",
            "research",
            "publications",
            "citations",
            "patents",
            "faculty",
        ),
        ResearchDimension.PLACEMENTS: (
            "placements",
            "placement",
            "placement report",
            "median salary",
            "recruiters",
        ),
        ResearchDimension.PERCEPTION_INFRASTRUCTURE: (
            "perception",
            "infrastructure",
            "alumni",
            "campus",
            "student life",
        ),
    }


def test_validated_entity_and_any_configured_term_are_accepted(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        title="VIKAT.AI company profile",
        content="Recent investors shared an update.",
    )

    observation = _assessment(company_entity, result)

    assert observation.status is ResearchFilterStatus.ACCEPTED
    assert observation.reason is ResearchFilterReason.VALIDATED_AND_RELEVANT
    assert observation.relevance.status is DimensionRelevanceStatus.RELEVANT
    assert observation.relevance.matched_terms == ("investors",)


def test_matching_is_case_insensitive_and_respects_word_boundaries(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        title="VIKAT.AI and DEVALUATION",
        content="No other relevant details.",
    )

    observation = _assessment(company_entity, result)

    assert observation.status is ResearchFilterStatus.REJECTED
    assert observation.relevance.status is DimensionRelevanceStatus.IRRELEVANT
    assert observation.relevance.matched_terms == ()


def test_entity_name_itself_does_not_make_dimension_relevant(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        dimension=ResearchDimension.ENGINEERING_TECHNICAL,
        title="VIKAT.AI profile",
        content="A general organizational profile with no work-area details.",
    )

    observation = _assessment(company_entity, result)

    assert observation.status is ResearchFilterStatus.REJECTED
    assert observation.relevance.matched_terms == ()


def test_query_membership_does_not_make_result_relevant(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        title="VIKAT.AI overview",
        content="General information without domain terms.",
    )
    result = result.model_copy(update={"query": '"VIKAT.AI" funding valuation revenue investors'})

    observation = _assessment(company_entity, result)

    assert "funding" in result.query
    assert observation.status is ResearchFilterStatus.REJECTED
    assert observation.reason is ResearchFilterReason.DIMENSION_IRRELEVANT
    assert observation.relevance.reason is DimensionRelevanceReason.NO_CONFIGURED_TERM_MATCH


def test_phrase_term_works_but_standalone_the_does_not_match_ranking(
    college_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        entity_type=ResearchEntityType.COLLEGE,
        dimension=ResearchDimension.OFFICIAL_RANKING,
        title="IIT Patna in THE ranking",
        content="A ranking report.",
    )
    observation = _assessment(college_entity, result)
    assert observation.status is ResearchFilterStatus.ACCEPTED
    assert "THE ranking" in observation.relevance.matched_terms

    unrelated = research_result_factory(
        entity_type=ResearchEntityType.COLLEGE,
        dimension=ResearchDimension.OFFICIAL_RANKING,
        title="IIT Patna is the institute",
        content="General institutional information only.",
        result_id="result-2",
    )
    unrelated_observation = _assessment(college_entity, unrelated)
    assert unrelated_observation.status is ResearchFilterStatus.REJECTED


def test_ambiguous_entity_is_not_relevance_promoted(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        title="Company information",
        content="Investors discussed a business.",
    )

    observation = _assessment(company_entity, result)

    assert observation.validation.status is EntityValidationStatus.AMBIGUOUS
    assert observation.status is ResearchFilterStatus.AMBIGUOUS
    assert observation.relevance.status is DimensionRelevanceStatus.NOT_EVALUATED
    assert observation.relevance.matched_terms == ()


def test_rejected_entity_is_not_accepted_even_when_relevant(
    company_entity,
    research_result_factory,
) -> None:
    from vikat_hire.research.validation import validate_research_entity

    other = company_entity.model_copy(update={"entity_id": "other", "name": "Other Company"})
    result = research_result_factory(
        title="Other Company funding",
        content="Investors discussed revenue.",
    )
    validation = validate_research_entity(
        entity=company_entity,
        result=result,
        known_entities=(other,),
    )

    observation = filter_research_evidence(
        entity=company_entity,
        result=result,
        validation=validation,
    )

    assert validation.status is EntityValidationStatus.REJECTED
    assert observation.status is ResearchFilterStatus.REJECTED
    assert observation.reason is ResearchFilterReason.ENTITY_REJECTED
    assert observation.relevance.status is DimensionRelevanceStatus.NOT_EVALUATED


def test_filtering_preserves_decision_chain_and_provenance(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory()
    observation = _assessment(company_entity, result)

    assert observation.result == result
    assert observation.validation.result_id == result.result_id
    assert observation.relevance.validation_decision_id == (observation.validation.decision_id)
    assert set(result.provenance_refs).issubset(observation.provenance_refs)
    assert set(company_entity.provenance_refs).issubset(observation.provenance_refs)


def test_filtering_is_deterministic(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory()
    assert _assessment(company_entity, result) == _assessment(company_entity, result)


def test_relevance_decision_id_is_bound_to_result_content(
    company_entity,
    research_result_factory,
) -> None:
    first_result = research_result_factory(title="VIKAT.AI funding")
    changed_result = research_result_factory(
        title="VIKAT.AI funding",
        content="Changed evidence description.",
    )
    first = _assessment(company_entity, first_result)
    repeated = _assessment(company_entity, first_result)
    changed = _assessment(company_entity, changed_result)

    assert first.relevance.decision_id == repeated.relevance.decision_id
    assert first.relevance.decision_id != changed.relevance.decision_id


def test_mismatched_validation_reference_fails_loudly(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory()
    validation = validate_research_entity(entity=company_entity, result=result)
    wrong = validation.model_copy(update={"result_id": "different"})

    with pytest.raises(ResearchEvidenceFilteringError, match="result_id"):
        filter_research_evidence(
            entity=company_entity,
            result=result,
            validation=wrong,
        )
