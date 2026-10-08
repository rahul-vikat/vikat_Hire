from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from vikat_hire.collection.github import GitHubCollector
from vikat_hire.collection.linkedin import LinkedInCollector
from vikat_hire.collection.portfolio import PortfolioCollector
from vikat_hire.config.jd_classification import JDClassificationConfiguration
from vikat_hire.contracts.common import (
    AccessStatus,
    ApplicabilityStatus,
    DatePrecision,
    DerivationMethod,
    DimensionName,
    DimensionResolution,
    EvidenceConfidence,
    EvidenceStatus,
    InputKind,
    Provenance,
    RequirementCategory,
    RequirementImportance,
    SourceType,
)
from vikat_hire.contracts.evaluation import EvaluationResult
from vikat_hire.contracts.explanation import ExplanationResult
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.normalization import (
    JDExperienceRequirement,
    NormalizationResult,
    NormalizedExperienceRecord,
    NormalizedResponsibility,
)
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.jd_aligned_experience import (
    aggregate_jd_aligned_experience,
)
from vikat_hire.evaluation.keyword_matcher import KeywordDefinition
from vikat_hire.evaluation.semantic_fit import aggregate_semantic_fit
from vikat_hire.normalization.document import extract_document_text
from vikat_hire.orchestration.graph import (
    JD_CONTENT_CONFIG_KEY,
    RESUME_CONTENT_CONFIG_KEY,
    ScreeningGraphConfigurationError,
    ScreeningGraphDependencies,
    _require_dimensions_inputs,
    build_screening_graph,
    invoke_screening_graph,
)
from vikat_hire.orchestration.nodes.calculate_score import calculate_score_node
from vikat_hire.orchestration.state import (
    from_orchestration_state,
    to_orchestration_state,
)


class _Fetcher:
    def __init__(self, text: str = "Python services") -> None:
        self.text = text
        self.calls: list[str] = []

    def fetch(self, *, url: str) -> str:
        self.calls.append(url)
        return self.text


def _dependencies(
    *,
    linkedin_fetcher: _Fetcher | None = None,
    github_fetcher: _Fetcher | None = None,
    portfolio_fetcher: _Fetcher | None = None,
) -> ScreeningGraphDependencies:
    return ScreeningGraphDependencies(
        classification_configuration=JDClassificationConfiguration(
            configuration_ref="jd-classification-test@1",
            technical_indicators=("python",),
            non_technical_indicators=("communications role",),
        ),
        linkedin_collector=LinkedInCollector(linkedin_fetcher or _Fetcher()),
        github_collector=GitHubCollector(github_fetcher or _Fetcher()),
        portfolio_collector=PortfolioCollector(portfolio_fetcher or _Fetcher()),
        scoring_release="verifyhire-scoring@2.2.0",
        policy_configuration_ref="policy-test@1",
        explanation_generator=lambda context: ExplanationResult(
            screening_id=context.screening_id,
            summary="Deterministic test explanation.",
            dimensions=(),
            generated_by="test",
            evidence_refs=(),
        ),
    )


def _state(*, technical: bool = False, with_external_urls: bool = False) -> ScreeningState:
    screening_id = "graph-screening-1"
    jd = DocumentInput(
        input_id="jd-1",
        kind=InputKind.JD,
        filename="jd.txt",
        media_type="text/plain",
        content_hash="jd-hash",
        storage_ref="opaque/jd",
    )
    resume = DocumentInput(
        input_id="resume-1",
        kind=InputKind.RESUME,
        filename="resume.txt",
        media_type="text/plain",
        content_hash="resume-hash",
        storage_ref="opaque/resume",
    )
    provenances = tuple(
        Provenance(
            provenance_id=f"{kind.value}-provenance",
            source_type=source_type,
            source_ref=document.input_id,
            method=DerivationMethod.PARSER,
            access_status=AccessStatus.AUTHORIZED,
        )
        for kind, source_type, document in (
            (InputKind.JD, SourceType.JD_FILE, jd),
            (InputKind.RESUME, SourceType.RESUME_FILE, resume),
        )
    )
    external = {}
    if with_external_urls:
        external = {
            "linkedin_url": "https://www.linkedin.com/in/graph-user",
            "github_url": "https://github.com/graph-user",
            "portfolio_url": "https://portfolio.example/profile",
        }
    return ScreeningState(
        screening_id=screening_id,
        screening_input=ScreeningInput(
            screening_id=screening_id,
            jd=jd,
            resume=resume,
            external_sources={"input_id": "external-1", **external},
        ),
        provenances=provenances,
        current_node="start",
    )


def _invoke(graph, state: ScreeningState, *, jd: bytes, resume: bytes, thread_id: str):
    return invoke_screening_graph(
        graph,
        state,
        jd_content=jd,
        resume_content=resume,
        config={"configurable": {"thread_id": thread_id}},
    )


def test_graph_builds_with_injected_memory_checkpointer() -> None:
    graph = build_screening_graph(
        dependencies=_dependencies(),
        checkpointer=MemorySaver(),
    )

    assert graph is not None
    graph_edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}
    assert ("assemble_evidence", "evaluate_dimensions") in graph_edges


def test_graph_rejects_malformed_dependencies() -> None:
    with pytest.raises(ScreeningGraphConfigurationError, match="dependencies"):
        build_screening_graph(dependencies=object())  # type: ignore[arg-type]


def test_nontechnical_flow_skips_github_and_portfolio_and_preserves_seniority() -> None:
    github_fetcher = _Fetcher()
    portfolio_fetcher = _Fetcher()
    graph = build_screening_graph(
        dependencies=_dependencies(
            github_fetcher=github_fetcher,
            portfolio_fetcher=portfolio_fetcher,
        ),
        checkpointer=MemorySaver(),
    )
    state = _state()
    jd = b"Must have: communications role\nWorks under supervision."
    resume = b"Communications role\nWorked under supervision."

    output = _invoke(graph, state, jd=jd, resume=resume, thread_id="nontechnical")
    final_state, blocks, normalization = from_orchestration_state(output)

    assert github_fetcher.calls == []
    assert portfolio_fetcher.calls == []
    assert len(blocks) == 2
    assert normalization is not None
    assert final_state.evaluation is not None
    assert normalization is not None
    dimensions = {item.dimension: item for item in final_state.evaluation.dimensions}
    assert set(dimensions) == set(DimensionName) - {
        DimensionName.GITHUB_EVIDENCE,
        DimensionName.PORTFOLIO_EVIDENCE,
    }
    expected_semantic = aggregate_semantic_fit(
        requirements=normalization.jd_requirements,
        matches=final_state.deterministic_semantic_matches,
    )
    semantic = dimensions[DimensionName.SEMANTIC_FIT]
    assert semantic.model_dump(exclude={"dimension_id", "created_at"}) == (
        expected_semantic.model_dump(exclude={"dimension_id", "created_at"})
    )
    expected_experience = aggregate_jd_aligned_experience(
        requirement_ids=tuple(
            requirement.requirement_id for requirement in normalization.jd_experience_requirements
        ),
        evaluations=(),
    )
    experience = dimensions[DimensionName.JD_ALIGNED_EXPERIENCE]
    assert experience.model_dump(exclude={"dimension_id", "created_at"}) == (
        expected_experience.model_dump(exclude={"dimension_id", "created_at"})
    )
    assert experience.resolution is DimensionResolution.EXCLUDED
    assert experience.raw_value is None
    assert DimensionName.GITHUB_EVIDENCE not in dimensions
    assert DimensionName.PORTFOLIO_EVIDENCE not in dimensions
    seniority = tuple(
        item
        for item in final_state.evaluation.dimensions
        if item.dimension is DimensionName.SENIORITY_SCOPE_ALIGNMENT
    )
    assert len(seniority) == 1
    assert seniority[0].raw_value == Decimal("100")
    must_have = dimensions[DimensionName.MUST_HAVE_COVERAGE]
    assert must_have.resolution is DimensionResolution.EXCLUDED
    assert must_have.raw_value is None
    assert final_state.score is not None
    assert final_state.policy is not None
    assert final_state.explanation is not None


def test_graph_dimension_assembly_evaluates_aligned_experience() -> None:
    state = _state()
    requirement = JDExperienceRequirement(
        requirement_id="jd-exp-1",
        category=RequirementCategory.EXPERIENCE,
        importance=RequirementImportance.MUST_HAVE,
        text="payment APIs",
        source_type=SourceType.JD_FILE,
        source_ref="jd-1",
        evidence_refs=("jd-evidence-1",),
        provenance_refs=("jd-provenance",),
        minimum_years=Decimal("3"),
    )
    record = NormalizedExperienceRecord(
        record_id="linkedin-exp-1",
        employer="Example",
        role="Payment API Engineer",
        start_date=date(2020, 1, 1),
        end_date=date(2022, 12, 31),
        date_precision=DatePrecision.YEAR,
        current=False,
        responsibility_refs=("linkedin-resp-1",),
        source_text="Build payment APIs for merchants.",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-profile-1",
        evidence_refs=("linkedin-evidence-1",),
        provenance_refs=("linkedin-provenance",),
    )
    responsibility = NormalizedResponsibility(
        responsibility_id="linkedin-resp-1",
        text="Build payment APIs for merchants.",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-profile-1",
        evidence_status=EvidenceStatus.SUPPORTED,
        evidence_refs=("linkedin-evidence-1",),
        provenance_refs=("linkedin-provenance",),
        confidence=EvidenceConfidence.MEDIUM,
    )
    normalization = NormalizationResult(
        screening_id=state.screening_id,
        jd_experience_requirements=(requirement,),
        experience_records=(record,),
        responsibilities=(responsibility,),
    )
    transport = to_orchestration_state(
        state,
        extracted_blocks=(),
        normalization=normalization,
    )

    _, dimensions, _ = _require_dimensions_inputs(transport)

    experience = next(
        item for item in dimensions if item.dimension is DimensionName.JD_ALIGNED_EXPERIENCE
    )
    assert experience.resolution is DimensionResolution.EVALUATED
    assert experience.raw_value == Decimal("100.00")
    assert experience.requirement_refs == ("jd-exp-1",)
    assert experience.evidence_refs == ("linkedin-evidence-1",)
    assert experience.provenance_refs == (
        "jd-provenance",
        "linkedin-provenance",
    )

    scored = calculate_score_node(
        state.model_copy(
            update={
                "evaluation": EvaluationResult(
                    screening_id=state.screening_id,
                    dimensions=dimensions,
                    deterministic=True,
                )
            }
        ),
        scoring_release="verifyhire-scoring@2.2.0",
    )
    assert scored.score is not None
    experience_audit = next(
        item for item in scored.score.audit if item.dimension is DimensionName.JD_ALIGNED_EXPERIENCE
    )
    assert experience_audit.weight == Decimal("20")
    assert experience_audit.evidence_refs == ("linkedin-evidence-1",)


def test_graph_end_to_end_produces_jd_aligned_experience_and_score() -> None:
    linkedin_fetcher = _Fetcher(
        '{"experience":[{"position":"Payment API Engineer",'
        '"companyName":"Example",'
        '"startDate":{"month":1,"year":2020},'
        '"endDate":{"month":12,"year":2022},'
        '"description":"Build payment APIs for merchant services."}]}'
    )
    state = _state(with_external_urls=True)
    jd_content = (
        b"Required: 3 years experience building payment APIs\n"
        b"Must have: Python\nOwn services end-to-end."
    )
    jd_block = extract_document_text(
        document=state.screening_input.jd,
        content=jd_content,
        provenance_refs=("jd_file-provenance",),
    )[0]
    requirement_id = f"{jd_block.block_id}:line:1"
    dependencies = replace(
        _dependencies(linkedin_fetcher=linkedin_fetcher),
        keyword_vocabularies={
            requirement_id: KeywordDefinition(
                canonical_ref="payment-api",
                keywords=("payment APIs",),
            )
        },
    )
    graph = build_screening_graph(
        dependencies=dependencies,
        checkpointer=MemorySaver(),
    )

    output = _invoke(
        graph,
        state,
        jd=jd_content,
        resume=b"Payment API Engineer\nOwned services end-to-end.",
        thread_id="experience-alignment",
    )
    final_state, _, normalization = from_orchestration_state(output)

    assert normalization is not None
    assert linkedin_fetcher.calls == ["https://www.linkedin.com/in/graph-user"]
    assert final_state.evaluation is not None
    dimension = next(
        item
        for item in final_state.evaluation.dimensions
        if item.dimension is DimensionName.JD_ALIGNED_EXPERIENCE
    )
    assert dimension.resolution is DimensionResolution.EVALUATED
    assert dimension.raw_value == Decimal("100.00")
    assert dimension.requirement_refs == (requirement_id,)
    assert dimension.evidence_refs
    linkedin_provenance_ids = {
        item.provenance_id
        for item in final_state.provenances
        if item.source_type is SourceType.LINKEDIN
    }
    assert linkedin_provenance_ids
    assert linkedin_provenance_ids.issubset(dimension.provenance_refs)

    assert final_state.score is not None
    scored_dimension = next(
        item
        for item in final_state.score.dimensions
        if item.dimension is DimensionName.JD_ALIGNED_EXPERIENCE
    )
    assert scored_dimension.weight == Decimal("20")
    assert scored_dimension.raw_value == Decimal("100.00")


def test_technical_flow_runs_github_and_portfolio_in_order() -> None:
    github_fetcher = _Fetcher("Python backend services")
    portfolio_fetcher = _Fetcher("Python project portfolio")
    graph = build_screening_graph(
        dependencies=_dependencies(
            github_fetcher=github_fetcher,
            portfolio_fetcher=portfolio_fetcher,
        ),
        checkpointer=MemorySaver(),
    )
    output = _invoke(
        graph,
        _state(technical=True, with_external_urls=True),
        jd=b"Must have: Python\nOwn services end-to-end.",
        resume=b"Python\nOwned services end-to-end.",
        thread_id="technical",
    )
    state, _, _ = from_orchestration_state(output)

    assert github_fetcher.calls == ["https://github.com/graph-user"]
    assert portfolio_fetcher.calls == ["https://portfolio.example/profile"]
    assert state.evaluation is not None
    assert state.score is not None
    dimensions = {item.dimension: item for item in state.evaluation.dimensions}
    assert set(dimensions) == set(DimensionName)
    for dimension_name in (DimensionName.GITHUB_EVIDENCE, DimensionName.PORTFOLIO_EVIDENCE):
        assert dimensions[dimension_name].applicability is ApplicabilityStatus.APPLICABLE
        assert dimensions[dimension_name].resolution in {
            DimensionResolution.EVALUATED,
            DimensionResolution.EXCLUDED,
        }
        if dimensions[dimension_name].resolution is DimensionResolution.EXCLUDED:
            assert dimensions[dimension_name].raw_value is None
        else:
            assert dimensions[dimension_name].raw_value is not None
    assert DimensionName.SEMANTIC_FIT in dimensions
    assert DimensionName.JD_ALIGNED_EXPERIENCE in dimensions
    assert DimensionName.MUST_HAVE_COVERAGE in dimensions


def test_missing_documents_interrupt_and_resume_with_langgraph_command() -> None:
    graph = build_screening_graph(dependencies=_dependencies(), checkpointer=MemorySaver())
    state = _state()
    initial = to_orchestration_state(state, extracted_blocks=())
    config = {"configurable": {"thread_id": "resume-test"}}
    interrupted = graph.invoke(initial, config=config)
    assert "__interrupt__" in interrupted

    jd_blocks = extract_document_text(
        document=state.screening_input.jd,
        content=b"Must have: communications role\nWorks under supervision.",
        provenance_refs=(
            next(
                item.provenance_id
                for item in state.provenances
                if item.source_type is SourceType.JD_FILE
            ),
        ),
    )
    resume_blocks = extract_document_text(
        document=state.screening_input.resume,
        content=b"Communications role\nWorked under supervision.",
        provenance_refs=(
            next(
                item.provenance_id
                for item in state.provenances
                if item.source_type is SourceType.RESUME_FILE
            ),
        ),
    )
    incomplete_payload = {
        "screening_input": state.screening_input.model_dump(mode="json"),
        "extracted_blocks": tuple(block.model_dump(mode="json") for block in jd_blocks),
    }

    still_interrupted = graph.invoke(Command(resume=incomplete_payload), config=config)
    assert "__interrupt__" in still_interrupted

    complete_payload = {
        "screening_input": state.screening_input.model_dump(mode="json"),
        "extracted_blocks": tuple(
            block.model_dump(mode="json") for block in (*jd_blocks, *resume_blocks)
        ),
    }
    completed = graph.invoke(Command(resume=complete_payload), config=config)
    final_state, _, _ = from_orchestration_state(completed)
    assert final_state.evaluation is not None


def test_raw_bytes_are_not_part_of_domain_or_transport_state() -> None:
    state = _state()
    transport = to_orchestration_state(state, extracted_blocks=())
    serialized = repr(transport)

    assert JD_CONTENT_CONFIG_KEY not in transport
    assert RESUME_CONTENT_CONFIG_KEY not in transport
    assert b"raw JD" not in serialized.encode()
    assert "content" not in state.screening_input.jd.model_fields_set
    assert "content" not in state.screening_input.resume.model_fields_set


def test_seniority_weight_is_applied_only_by_authoritative_scoring_layer() -> None:
    graph = build_screening_graph(dependencies=_dependencies(), checkpointer=MemorySaver())
    output = _invoke(
        graph,
        _state(),
        jd=b"Must have: communications role\nWorks under supervision.",
        resume=b"Communications role\nWorked under supervision.",
        thread_id="weight-test",
    )
    state, _, _ = from_orchestration_state(output)

    assert state.evaluation is not None
    seniority = next(
        item
        for item in state.evaluation.dimensions
        if item.dimension.value == "seniority_scope_alignment"
    )
    assert seniority.raw_value is None or isinstance(seniority.raw_value, Decimal)
    assert state.score is not None
    seniority_score = next(
        item
        for item in state.score.dimensions
        if item.dimension.value == "seniority_scope_alignment"
    )
    assert seniority_score.weight == Decimal("10")
    if seniority.resolution.value == "evaluated":
        seniority_audit = next(
            item
            for item in state.score.audit
            if item.dimension.value == "seniority_scope_alignment"
        )
        assert seniority_audit.weight == Decimal("10")
        assert seniority_audit.configuration_ref == "verifyhire-scoring@2.2.0"
