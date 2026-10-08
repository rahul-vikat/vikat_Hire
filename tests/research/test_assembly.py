from __future__ import annotations

import pytest

from vikat_hire.contracts.research import (
    COLLEGE_DIMENSIONS,
    COMPANY_DIMENSIONS,
    ResearchDimension,
    ResearchEntityType,
    ResearchFilterStatus,
)
from vikat_hire.research.assembly import (
    ResearchEvidenceAssemblyError,
    assemble_research_evidence,
)
from vikat_hire.research.filtering import filter_research_evidence
from vikat_hire.research.validation import validate_research_entity


def _assessment(entity, result):
    return filter_research_evidence(
        entity=entity,
        result=result,
        validation=validate_research_entity(entity=entity, result=result),
    )


def test_assembly_has_all_dimensions_and_only_accepted_evidence(
    company_entity,
    research_result_factory,
) -> None:
    accepted_result = research_result_factory(result_id="accepted")
    irrelevant_result = research_result_factory(
        title="VIKAT.AI overview",
        content="A general company description.",
        result_id="irrelevant",
        result_index=1,
    )
    accepted = _assessment(company_entity, accepted_result)
    rejected = _assessment(company_entity, irrelevant_result)

    (assembly,) = assemble_research_evidence(
        entities=(company_entity,),
        observations=(accepted, rejected),
    )

    assert tuple(group.dimension for group in assembly.dimensions) == COMPANY_DIMENSIONS
    financial = assembly.dimensions[0]
    assert [item.result_id for item in financial.accepted_evidence] == ["accepted"]
    assert [item.status for item in assembly.audited_observations] == [
        ResearchFilterStatus.ACCEPTED,
        ResearchFilterStatus.REJECTED,
    ]
    assert assembly.dimensions[1].accepted_evidence == ()
    accepted_evidence = financial.accepted_evidence[0]
    assert accepted_evidence.validation_decision_id == accepted.validation.decision_id
    assert accepted_evidence.relevance_decision_id == accepted.relevance.decision_id
    assert set(accepted_result.provenance_refs).issubset(accepted_evidence.provenance_refs)
    assert set(accepted_evidence.provenance_refs).issubset(assembly.provenance_refs)
    assert accepted_evidence.observation_id == accepted.observation_id


def test_assembly_keeps_empty_dimensions_for_college(
    college_entity,
) -> None:
    (assembly,) = assemble_research_evidence(
        entities=(college_entity,),
        observations=(),
    )

    assert tuple(group.dimension for group in assembly.dimensions) == COLLEGE_DIMENSIONS
    assert all(not group.accepted_evidence for group in assembly.dimensions)
    assert assembly.audited_observations == ()


def test_assembly_retains_ambiguous_observations_but_not_as_evidence(
    company_entity,
    research_result_factory,
) -> None:
    result = research_result_factory(
        title="Company information",
        content="A general article.",
    )
    observation = _assessment(company_entity, result)

    (assembly,) = assemble_research_evidence(
        entities=(company_entity,),
        observations=(observation,),
    )

    assert assembly.audited_observations == (observation,)
    assert all(not group.accepted_evidence for group in assembly.dimensions)


def test_duplicate_search_observations_are_not_silently_collapsed(
    company_entity,
    research_result_factory,
) -> None:
    first_result = research_result_factory(result_id="duplicate-a", result_index=0)
    second_result = research_result_factory(result_id="duplicate-b", result_index=1)
    observations = (
        _assessment(company_entity, first_result),
        _assessment(company_entity, second_result),
    )

    (assembly,) = assemble_research_evidence(
        entities=(company_entity,),
        observations=observations,
    )

    assert len(assembly.audited_observations) == 2
    assert [item.result.result_id for item in assembly.audited_observations] == [
        "duplicate-a",
        "duplicate-b",
    ]
    assert [item.result_id for item in assembly.dimensions[0].accepted_evidence] == [
        "duplicate-a",
        "duplicate-b",
    ]


def test_duplicate_observations_fail_loudly(
    company_entity,
    research_result_factory,
) -> None:
    observation = _assessment(company_entity, research_result_factory())

    with pytest.raises(ResearchEvidenceAssemblyError, match="duplicate observation_id"):
        assemble_research_evidence(
            entities=(company_entity,),
            observations=(observation, observation),
        )


def test_unknown_entity_observation_fails_loudly(
    company_entity,
    college_entity,
    research_result_factory,
) -> None:
    observation = _assessment(company_entity, research_result_factory())

    with pytest.raises(ResearchEvidenceAssemblyError, match="unknown research entity"):
        assemble_research_evidence(
            entities=(college_entity,),
            observations=(observation,),
        )


def test_assembly_order_is_deterministic(
    company_entity,
    research_result_factory,
    college_entity,
) -> None:
    company_observation = _assessment(
        company_entity,
        research_result_factory(result_id="company-result"),
    )
    college_result = research_result_factory(
        entity_type=ResearchEntityType.COLLEGE,
        dimension=ResearchDimension.OFFICIAL_RANKING,
        title="IIT Patna ranking",
        content="NIRF ranking information.",
        result_id="college-result",
    )
    college_observation = _assessment(college_entity, college_result)

    kwargs = {
        "entities": (college_entity, company_entity),
        "observations": (college_observation, company_observation),
    }
    first = assemble_research_evidence(**kwargs)
    second = assemble_research_evidence(**kwargs)

    assert first == second
    assert [item.entity.entity_type for item in first] == [
        ResearchEntityType.COLLEGE,
        ResearchEntityType.COMPANY,
    ]
