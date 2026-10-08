"""LangGraph boundary for one screening execution.

Raw document bytes are invocation configuration, never graph/domain state. Pass
them under :data:`JD_CONTENT_CONFIG_KEY` and :data:`RESUME_CONTENT_CONFIG_KEY`
in ``configurable``. A caller-supplied LangGraph checkpointer owns execution
resume; the domain CheckpointStore is intentionally not involved here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from vikat_hire.ai import ExplanationProvider
from vikat_hire.ai.llm_semantic import LLMSemanticMatcher
from vikat_hire.collection.github import GitHubCollector
from vikat_hire.collection.linkedin import LinkedInCollector
from vikat_hire.collection.portfolio import PortfolioCollector
from vikat_hire.collection.resume_extractor import OCRTextExtractor
from vikat_hire.config.jd_classification import JDClassificationConfiguration
from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    RequirementImportance,
    SourceType,
)
from vikat_hire.contracts.normalization import NormalizationResult
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.dimensions import evaluate_dimension
from vikat_hire.evaluation.keyword_matcher import KeywordDefinition
from vikat_hire.evaluation.must_have import evaluate_must_have
from vikat_hire.evaluation.nice_to_have import evaluate_nice_to_have
from vikat_hire.evaluation.requirement import evaluate_requirement
from vikat_hire.normalization.external import normalize_external_sources
from vikat_hire.orchestration.interrupts import (
    interrupt_missing_input,
    validate_input_state,
)
from vikat_hire.orchestration.nodes.apply_external_normalization import (
    apply_external_normalization_node,
)
from vikat_hire.orchestration.nodes.apply_normalization import apply_normalization_node
from vikat_hire.orchestration.nodes.assemble_evidence import assemble_evidence_node
from vikat_hire.orchestration.nodes.calculate_score import calculate_score_node
from vikat_hire.orchestration.nodes.classify_jd import classify_jd_node
from vikat_hire.orchestration.nodes.collect_github import collect_github_node
from vikat_hire.orchestration.nodes.collect_linkedin import collect_linkedin_node
from vikat_hire.orchestration.nodes.collect_portfolio import collect_portfolio_node
from vikat_hire.orchestration.nodes.evaluate_dimensions import evaluate_dimensions_node
from vikat_hire.orchestration.nodes.evaluate_github import evaluate_github_node
from vikat_hire.orchestration.nodes.evaluate_linkedin import evaluate_linkedin_node
from vikat_hire.orchestration.nodes.evaluate_policy import evaluate_policy_node
from vikat_hire.orchestration.nodes.evaluate_portfolio import evaluate_portfolio_node
from vikat_hire.orchestration.nodes.evaluate_seniority import evaluate_seniority_node
from vikat_hire.orchestration.nodes.extract_jd import extract_jd_node
from vikat_hire.orchestration.nodes.extract_resume import extract_resume_node
from vikat_hire.orchestration.nodes.generate_explanation import generate_explanation_node
from vikat_hire.orchestration.nodes.match_keywords import match_keywords_node
from vikat_hire.orchestration.nodes.match_llm_semantic import match_llm_semantic_node
from vikat_hire.orchestration.nodes.match_semantic import match_semantic_node
from vikat_hire.orchestration.nodes.normalize import normalize_node
from vikat_hire.orchestration.routing import (
    NODE_CALCULATE_SCORE,
    NODE_CLASSIFY_JD,
    NODE_END,
    NODE_EVALUATE_DIMENSIONS,
    NODE_EVALUATE_GITHUB,
    NODE_EVALUATE_LINKEDIN,
    NODE_EVALUATE_POLICY,
    NODE_EVALUATE_PORTFOLIO,
    NODE_GENERATE_EXPLANATION,
    NODE_INTERRUPT,
    NODE_MATCH_KEYWORDS,
    NODE_REVIEW,
    NODE_VALIDATE_INPUT,
    route_after_classification,
    route_after_dimensions,
    route_after_github,
    route_after_input_validation,
    route_after_linkedin_evidence,
    route_after_policy,
    route_after_portfolio,
    route_after_score,
    route_after_semantic_matching,
)
from vikat_hire.orchestration.state import (
    OrchestrationState,
    from_orchestration_state,
    to_orchestration_state,
)
from vikat_hire.policy.evaluator import MANDATORY_GATES

JD_CONTENT_CONFIG_KEY = "vikat_hire_jd_content"
RESUME_CONTENT_CONFIG_KEY = "vikat_hire_resume_content"


class ScreeningGraphConfigurationError(ValueError):
    """Invalid graph dependency or invocation configuration."""


@dataclass(frozen=True)
class ScreeningGraphDependencies:
    """Explicit runtime dependencies used by the screening graph."""

    classification_configuration: JDClassificationConfiguration
    linkedin_collector: LinkedInCollector
    github_collector: GitHubCollector
    portfolio_collector: PortfolioCollector
    scoring_release: str
    policy_field_presence: Mapping[str, bool]
    policy_configuration_ref: str
    explanation_generator: ExplanationProvider
    keyword_vocabularies: Mapping[str, KeywordDefinition] | None = None
    llm_semantic_matcher: LLMSemanticMatcher | None = None
    ocr_text_extractor: OCRTextExtractor | None = None

    def __post_init__(self) -> None:
        expected = (
            (
                "classification_configuration",
                self.classification_configuration,
                JDClassificationConfiguration,
            ),
            ("linkedin_collector", self.linkedin_collector, LinkedInCollector),
            ("github_collector", self.github_collector, GitHubCollector),
            ("portfolio_collector", self.portfolio_collector, PortfolioCollector),
        )
        for name, value, expected_type in expected:
            if not isinstance(value, expected_type):
                raise ScreeningGraphConfigurationError(f"{name} must be a {expected_type.__name__}")
        if not isinstance(self.scoring_release, str) or not self.scoring_release.strip():
            raise ScreeningGraphConfigurationError("scoring_release must not be blank")
        if (
            not isinstance(self.policy_configuration_ref, str)
            or not self.policy_configuration_ref.strip()
        ):
            raise ScreeningGraphConfigurationError("policy_configuration_ref must not be blank")
        if not callable(self.explanation_generator):
            raise ScreeningGraphConfigurationError("explanation_generator must be callable")
        if self.llm_semantic_matcher is not None and not isinstance(
            self.llm_semantic_matcher, LLMSemanticMatcher
        ):
            raise ScreeningGraphConfigurationError(
                "llm_semantic_matcher must be an LLMSemanticMatcher or None"
            )
        if self.policy_field_presence is None:
            raise ScreeningGraphConfigurationError("policy_field_presence is required")
        unknown_fields = set(self.policy_field_presence) - set(MANDATORY_GATES)
        if unknown_fields:
            raise ScreeningGraphConfigurationError(
                "unsupported policy field names: " + ", ".join(sorted(unknown_fields))
            )
        if any(not isinstance(value, bool) for value in self.policy_field_presence.values()):
            raise ScreeningGraphConfigurationError("policy_field_presence values must be booleans")
        if self.keyword_vocabularies is not None:
            if any(
                not isinstance(key, str)
                or not key.strip()
                or not isinstance(value, KeywordDefinition)
                for key, value in self.keyword_vocabularies.items()
            ):
                raise ScreeningGraphConfigurationError(
                    "keyword_vocabularies must map requirement IDs to KeywordDefinition"
                )


def _read(
    transport: OrchestrationState,
) -> tuple[ScreeningState, tuple, NormalizationResult | None]:
    return from_orchestration_state(transport)


def _write(transport: OrchestrationState, state: ScreeningState, blocks: tuple, normalization):
    return to_orchestration_state(
        state,
        extracted_blocks=blocks,
        normalization=normalization,
    )


def _checkpoint_safe_transport(transport: OrchestrationState) -> OrchestrationState:
    """Convert validated contracts to serializer-safe JSON primitives."""
    state, blocks, normalization = from_orchestration_state(transport)
    return {
        "screening_state": json.loads(state.model_dump_json()),
        "extracted_blocks": [json.loads(block.model_dump_json()) for block in blocks],
        "normalization": (
            None if normalization is None else json.loads(normalization.model_dump_json())
        ),
    }


def _document_provenance_refs(state: ScreeningState, source_type: SourceType) -> tuple[str, ...]:
    document = (
        state.screening_input.jd
        if source_type is SourceType.JD_FILE
        else state.screening_input.resume
    )
    refs = tuple(
        item.provenance_id
        for item in state.provenances
        if item.source_type is source_type and item.source_ref == document.input_id
    )
    if not refs:
        raise ScreeningGraphConfigurationError(
            f"initial ScreeningState requires {source_type.value} provenance for "
            f"input {document.input_id!r}"
        )
    return refs


def _external_normalization(transport: OrchestrationState, source_type: SourceType):
    state, blocks, normalization = _read(transport)
    relevant = tuple(block for block in blocks if block.source_type is source_type)
    return normalize_external_sources(
        blocks=relevant,
        screening_id=state.screening_id,
    )


def _merge_external_normalization(transport: OrchestrationState, external) -> OrchestrationState:
    state, blocks, base = _read(transport)
    if base is None:
        raise ScreeningGraphConfigurationError("base normalization is required")
    combined = base.model_copy(
        update={
            "extracted_blocks": blocks,
            "claims": (*base.claims, *external.claims),
            "skills": (*base.skills, *external.skills),
            "responsibilities": (*base.responsibilities, *external.responsibilities),
            "experience_records": (*base.experience_records, *external.experience_records),
            "scope_evidence": (*base.scope_evidence, *external.scope_evidence),
            "provenance_refs": tuple(
                dict.fromkeys((*base.provenance_refs, *external.provenance_refs))
            ),
            "source_states": {**base.source_states, **external.source_states},
        }
    )
    return to_orchestration_state(state, extracted_blocks=blocks, normalization=combined)


def _matching_for_source(state: ScreeningState, requirements: tuple, vocabularies, source_type):
    source_provenance_ids = {
        provenance.provenance_id
        for provenance in state.provenances
        if provenance.source_type is source_type
    }
    claims = tuple(
        claim for claim in state.claims if source_provenance_ids.intersection(claim.provenance_refs)
    )
    working = state.model_copy(update={"claims": claims, "keyword_matches": ()})
    created = []
    for requirement in requirements:
        working = match_keywords_node(
            working,
            requirement=requirement,
            vocabulary=(vocabularies or {}).get(requirement.requirement_id),
        )
        added = tuple(
            item
            for item in working.keyword_matches
            if item.requirement_id == requirement.requirement_id
        )
        created.extend(added)
        working = working.model_copy(update={"keyword_matches": ()})
    existing_ids = {item.match_id for item in state.keyword_matches}
    duplicates = existing_ids.intersection(item.match_id for item in created)
    if duplicates:
        raise ScreeningGraphConfigurationError(
            "source-specific matching generated duplicate match IDs: "
            + ", ".join(sorted(duplicates))
        )
    return state.model_copy(update={"keyword_matches": (*state.keyword_matches, *created)})


def _require_normalization(transport: OrchestrationState) -> NormalizationResult:
    _, _, normalization = _read(transport)
    if normalization is None:
        raise ScreeningGraphConfigurationError("normalization is required")
    return normalization


def _require_dimensions_inputs(transport: OrchestrationState):
    state, _, normalization = _read(transport)
    if normalization is None:
        raise ScreeningGraphConfigurationError("normalization is required")
    requirements = normalization.jd_requirements
    evaluations = tuple(
        evaluate_requirement(
            requirement_id=requirement.requirement_id,
            matches=state.keyword_matches,
            candidate_claims=state.claims,
        )
        for requirement in requirements
    )
    dimensions = list(state.evaluation.dimensions if state.evaluation else ())
    for importance, evaluator, dimension_name in (
        (RequirementImportance.MUST_HAVE, evaluate_must_have, DimensionName.MUST_HAVE_COVERAGE),
        (
            RequirementImportance.NICE_TO_HAVE,
            evaluate_nice_to_have,
            DimensionName.NICE_TO_HAVE_COVERAGE,
        ),
    ):
        group = evaluator(
            evaluations=tuple(
                item
                for item in evaluations
                if next(
                    requirement.importance
                    for requirement in requirements
                    if requirement.requirement_id == item.requirement_id
                )
                is importance
            )
        )
        related_matches = tuple(
            match
            for match in state.keyword_matches
            if match.requirement_id in group.requirement_ids
        )
        provenance_refs = tuple(
            dict.fromkeys(
                reference for match in related_matches for reference in match.provenance_refs
            )
        )
        evidence_refs = tuple(
            dict.fromkeys(
                reference
                for item in evaluations
                if item.requirement_id in group.evaluated_requirement_ids
                for reference in item.evidence_refs
            )
        )
        dimensions.append(
            evaluate_dimension(
                dimension=dimension_name,
                applicability=ApplicabilityStatus.APPLICABLE,
                resolution=group.resolution,
                raw_value=group.raw_value,
                exclusion_reason=group.exclusion_reason,
                evidence_refs=evidence_refs,
                requirement_refs=group.requirement_ids,
                provenance_refs=provenance_refs,
                rationale=(
                    f"Deterministic {importance.value.replace('_', ' ')} requirement aggregation."
                ),
            )
        )
    return state, tuple(dimensions), normalization


def build_screening_graph(
    *,
    dependencies: ScreeningGraphDependencies,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Build a compiled graph using explicit dependencies and optional saver."""
    if not isinstance(dependencies, ScreeningGraphDependencies):
        raise ScreeningGraphConfigurationError("dependencies must be ScreeningGraphDependencies")

    builder = StateGraph(OrchestrationState)

    def extract_documents(transport: OrchestrationState, config: RunnableConfig):
        state, blocks, normalization = _read(transport)
        configurable = config.get("configurable", {})
        jd_bytes = configurable.get(JD_CONTENT_CONFIG_KEY)
        resume_bytes = configurable.get(RESUME_CONTENT_CONFIG_KEY)
        result = transport
        if jd_bytes is not None:
            result = extract_jd_node(
                result,
                content=jd_bytes,
                provenance_refs=_document_provenance_refs(state, SourceType.JD_FILE),
            )
        if resume_bytes is not None:
            result = extract_resume_node(
                result,
                content=resume_bytes,
                provenance_refs=_document_provenance_refs(state, SourceType.RESUME_FILE),
                ocr_text_extractor=dependencies.ocr_text_extractor,
            )
        return result

    def validate(transport: OrchestrationState):
        return validate_input_state(transport)

    def interrupt(transport: OrchestrationState):
        return interrupt_missing_input(transport)

    def normalize_and_apply(transport: OrchestrationState):
        return apply_normalization_node(normalize_node(transport))

    def classify(transport: OrchestrationState):
        state, _, normalization = _read(transport)
        if normalization is None:
            raise ScreeningGraphConfigurationError(
                "normalization is required before classification"
            )
        result = classify_jd_node(
            state,
            normalization=normalization,
            configuration=dependencies.classification_configuration,
        )
        return _write(transport, result, _read(transport)[1], normalization)

    def match_keywords(transport: OrchestrationState):
        state, _, normalization = _read(transport)
        requirements = _require_normalization(transport).jd_requirements
        for requirement in requirements:
            state = match_keywords_node(
                state,
                requirement=requirement,
                vocabulary=(dependencies.keyword_vocabularies or {}).get(
                    requirement.requirement_id
                ),
            )
        return _write(transport, state, _read(transport)[1], normalization)

    def match_semantic(transport: OrchestrationState):
        state, _, normalization = _read(transport)
        for requirement in _require_normalization(transport).jd_requirements:
            state = match_semantic_node(state, requirement=requirement)
            if dependencies.llm_semantic_matcher is not None:
                deterministic = next(
                    item
                    for item in state.deterministic_semantic_matches
                    if item.requirement_id == requirement.requirement_id
                )
                state = match_llm_semantic_node(
                    state,
                    requirement=requirement,
                    deterministic_match=deterministic,
                    matcher=dependencies.llm_semantic_matcher,
                )
        return _write(transport, state, _read(transport)[1], normalization)

    def linkedin(transport: OrchestrationState):
        _, _, normalization = _read(transport)
        collected = collect_linkedin_node(
            transport,
            collector=dependencies.linkedin_collector,
        )
        state, blocks, _ = _read(collected)
        return to_orchestration_state(
            state,
            extracted_blocks=blocks,
            normalization=normalization,
        )

    def normalize_linkedin(transport: OrchestrationState):
        external = _external_normalization(transport, SourceType.LINKEDIN)
        applied = apply_external_normalization_node(transport, normalization=external)
        return _merge_external_normalization(applied, external)

    def evaluate_linkedin(transport: OrchestrationState):
        state, blocks, normalization = _read(transport)
        result = evaluate_linkedin_node(state)
        return _write(transport, result, blocks, normalization)

    def seniority(transport: OrchestrationState):
        state, blocks, normalization = _read(transport)
        if normalization is None:
            raise ScreeningGraphConfigurationError("normalization is required for seniority")
        result = evaluate_seniority_node(state, normalization=normalization)
        return _write(transport, result, blocks, normalization)

    def github(transport: OrchestrationState):
        _, _, normalization = _read(transport)
        collected = collect_github_node(
            transport,
            collector=dependencies.github_collector,
        )
        state, blocks, _ = _read(collected)
        return to_orchestration_state(
            state,
            extracted_blocks=blocks,
            normalization=normalization,
        )

    def normalize_github(transport: OrchestrationState):
        external = _external_normalization(transport, SourceType.GITHUB)
        applied = apply_external_normalization_node(transport, normalization=external)
        state, blocks, normalization = _read(_merge_external_normalization(applied, external))
        matched = _matching_for_source(
            state,
            _require_normalization(transport).jd_requirements,
            dependencies.keyword_vocabularies,
            SourceType.GITHUB,
        )
        return _write(transport, matched, blocks, normalization)

    def evaluate_github(transport: OrchestrationState):
        state, blocks, normalization = _read(transport)
        result = evaluate_github_node(
            state,
            requirements=_require_normalization(transport).jd_requirements,
        )
        return _write(transport, result, blocks, normalization)

    def portfolio(transport: OrchestrationState):
        _, _, normalization = _read(transport)
        collected = collect_portfolio_node(
            transport,
            collector=dependencies.portfolio_collector,
        )
        state, blocks, _ = _read(collected)
        return to_orchestration_state(
            state,
            extracted_blocks=blocks,
            normalization=normalization,
        )

    def normalize_portfolio(transport: OrchestrationState):
        external = _external_normalization(transport, SourceType.PORTFOLIO)
        applied = apply_external_normalization_node(transport, normalization=external)
        state, blocks, normalization = _read(_merge_external_normalization(applied, external))
        matched = _matching_for_source(
            state,
            _require_normalization(transport).jd_requirements,
            dependencies.keyword_vocabularies,
            SourceType.PORTFOLIO,
        )
        return _write(transport, matched, blocks, normalization)

    def evaluate_portfolio(transport: OrchestrationState):
        state, blocks, normalization = _read(transport)
        result = evaluate_portfolio_node(
            state,
            requirements=_require_normalization(transport).jd_requirements,
        )
        return _write(transport, result, blocks, normalization)

    def evidence(transport: OrchestrationState):
        state, blocks, normalization = _read(transport)
        result = assemble_evidence_node(state)
        return _write(transport, result, blocks, normalization)

    def dimensions(transport: OrchestrationState):
        state, dimension_values, normalization = _require_dimensions_inputs(transport)
        contradiction_refs = (
            normalization.jd_scope_evidence
            and tuple(
                dict.fromkeys(
                    ref
                    for ref in (
                        state.jd_scope_evaluation.contradiction_evidence_refs
                        if state.jd_scope_evaluation is not None
                        else ()
                    )
                )
            )
        ) or ()
        result = evaluate_dimensions_node(
            state,
            dimensions=dimension_values,
            contradiction_refs=contradiction_refs,
        )
        return _write(transport, result, _read(transport)[1], normalization)

    def score(transport: OrchestrationState):
        state, blocks, normalization = _read(transport)
        result = calculate_score_node(state, scoring_release=dependencies.scoring_release)
        return _write(transport, result, blocks, normalization)

    def policy(transport: OrchestrationState):
        state, blocks, normalization = _read(transport)
        result = evaluate_policy_node(
            state,
            field_presence=dependencies.policy_field_presence,
            configuration_ref=dependencies.policy_configuration_ref,
            review_requests=state.pending_reviews,
        )
        return _write(transport, result, blocks, normalization)

    def review_boundary(transport: OrchestrationState):
        # Human review is an external workflow boundary; this graph preserves
        # pending reviews and terminates without inventing a second interrupt.
        return transport

    def explanation(transport: OrchestrationState):
        state, blocks, normalization = _read(transport)
        result = generate_explanation_node(state, generator=dependencies.explanation_generator)
        return _write(transport, result, blocks, normalization)

    for name, node in (
        ("extract_documents", extract_documents),
        (NODE_VALIDATE_INPUT, validate),
        (NODE_INTERRUPT, interrupt),
        ("normalize", normalize_and_apply),
        (NODE_CLASSIFY_JD, classify),
        (NODE_MATCH_KEYWORDS, match_keywords),
        ("match_semantic", match_semantic),
        ("collect_linkedin", linkedin),
        ("normalize_linkedin", normalize_linkedin),
        (NODE_EVALUATE_LINKEDIN, evaluate_linkedin),
        ("evaluate_seniority", seniority),
        ("collect_github", github),
        ("normalize_github", normalize_github),
        (NODE_EVALUATE_GITHUB, evaluate_github),
        ("collect_portfolio", portfolio),
        ("normalize_portfolio", normalize_portfolio),
        (NODE_EVALUATE_PORTFOLIO, evaluate_portfolio),
        ("assemble_evidence", evidence),
        (NODE_EVALUATE_DIMENSIONS, dimensions),
        (NODE_CALCULATE_SCORE, score),
        (NODE_EVALUATE_POLICY, policy),
        (NODE_REVIEW, review_boundary),
        (NODE_GENERATE_EXPLANATION, explanation),
    ):
        if name == "extract_documents":

            def safe_extraction_node(transport, config, *, _node=node):
                return _checkpoint_safe_transport(_node(transport, config))

            builder.add_node(name, safe_extraction_node)
        else:

            def safe_node(transport, *, _node=node):
                return _checkpoint_safe_transport(_node(transport))

            builder.add_node(name, safe_node)

    builder.add_edge(START, "extract_documents")
    builder.add_edge("extract_documents", NODE_VALIDATE_INPUT)
    builder.add_conditional_edges(
        NODE_VALIDATE_INPUT,
        lambda transport: _route_input(transport),
        {NODE_INTERRUPT: NODE_INTERRUPT, NODE_CLASSIFY_JD: "normalize"},
    )
    builder.add_edge(NODE_INTERRUPT, NODE_VALIDATE_INPUT)
    builder.add_edge("normalize", NODE_CLASSIFY_JD)
    builder.add_conditional_edges(
        NODE_CLASSIFY_JD,
        lambda transport: _route_classification(transport),
        {NODE_MATCH_KEYWORDS: NODE_MATCH_KEYWORDS, NODE_REVIEW: NODE_REVIEW},
    )
    builder.add_edge(NODE_MATCH_KEYWORDS, "match_semantic")
    builder.add_conditional_edges(
        "match_semantic",
        lambda transport: _route_semantic(transport),
        {NODE_EVALUATE_LINKEDIN: "collect_linkedin"},
    )
    builder.add_edge("collect_linkedin", "normalize_linkedin")
    builder.add_edge("normalize_linkedin", NODE_EVALUATE_LINKEDIN)
    builder.add_edge(NODE_EVALUATE_LINKEDIN, "evaluate_seniority")
    builder.add_conditional_edges(
        "evaluate_seniority",
        lambda transport: _route_linkedin(transport),
        {NODE_EVALUATE_GITHUB: "collect_github", NODE_EVALUATE_DIMENSIONS: "assemble_evidence"},
    )
    builder.add_edge("collect_github", "normalize_github")
    builder.add_edge("normalize_github", NODE_EVALUATE_GITHUB)
    builder.add_conditional_edges(
        NODE_EVALUATE_GITHUB,
        lambda transport: _route_github(transport),
        {"evaluate_portfolio": "collect_portfolio"},
    )
    builder.add_edge("collect_portfolio", "normalize_portfolio")
    builder.add_edge("normalize_portfolio", NODE_EVALUATE_PORTFOLIO)
    builder.add_conditional_edges(
        NODE_EVALUATE_PORTFOLIO,
        lambda transport: _route_portfolio(transport),
        {NODE_EVALUATE_DIMENSIONS: "assemble_evidence"},
    )
    builder.add_edge("assemble_evidence", NODE_EVALUATE_DIMENSIONS)
    builder.add_conditional_edges(
        NODE_EVALUATE_DIMENSIONS,
        lambda transport: _route_dimensions(transport),
        {NODE_CALCULATE_SCORE: NODE_CALCULATE_SCORE},
    )
    builder.add_conditional_edges(
        NODE_CALCULATE_SCORE,
        lambda transport: _route_score(transport),
        {NODE_EVALUATE_POLICY: NODE_EVALUATE_POLICY},
    )
    builder.add_conditional_edges(
        NODE_EVALUATE_POLICY,
        lambda transport: _route_policy(transport),
        {
            NODE_END: END,
            NODE_REVIEW: NODE_REVIEW,
            NODE_GENERATE_EXPLANATION: NODE_GENERATE_EXPLANATION,
        },
    )
    builder.add_edge(NODE_REVIEW, END)
    builder.add_conditional_edges(
        NODE_GENERATE_EXPLANATION,
        lambda transport: _route_explanation(transport),
        {NODE_END: END},
    )

    return builder.compile(checkpointer=checkpointer)


def _route_input(transport):
    state, _, _ = _read(transport)
    return route_after_input_validation(state)


def _route_classification(transport):
    state, _, _ = _read(transport)
    if state.classification is None and state.pending_reviews:
        return NODE_REVIEW
    return route_after_classification(state)


def _route_semantic(transport):
    return route_after_semantic_matching(_read(transport)[0])


def _route_linkedin(transport):
    return route_after_linkedin_evidence(_read(transport)[0])


def _route_github(transport):
    return route_after_github(_read(transport)[0])


def _route_portfolio(transport):
    return route_after_portfolio(_read(transport)[0])


def _route_dimensions(transport):
    return route_after_dimensions(_read(transport)[0])


def _route_score(transport):
    return route_after_score(_read(transport)[0])


def _route_policy(transport):
    return route_after_policy(_read(transport)[0])


def _route_explanation(transport):
    from vikat_hire.orchestration.routing import route_after_explanation

    return route_after_explanation(_read(transport)[0])


def invoke_screening_graph(
    graph,
    state: ScreeningState,
    *,
    jd_content: bytes | None,
    resume_content: bytes | None,
    config: RunnableConfig,
    extracted_blocks=(),
):
    """Invoke with detached state and raw bytes kept outside graph state."""
    if not isinstance(state, ScreeningState):
        raise ScreeningGraphConfigurationError("state must be a ScreeningState")
    if state.screening_input.screening_id != state.screening_id:
        raise ScreeningGraphConfigurationError("input screening_id does not match state")
    if not isinstance(config, dict):
        raise ScreeningGraphConfigurationError("config must be a mapping")
    configurable = dict(config.get("configurable", {}))
    for name, value in (("jd_content", jd_content), ("resume_content", resume_content)):
        if value is not None and not isinstance(value, bytes):
            raise ScreeningGraphConfigurationError(f"{name} must be bytes or None")
    if jd_content is not None:
        configurable[JD_CONTENT_CONFIG_KEY] = jd_content
    if resume_content is not None:
        configurable[RESUME_CONTENT_CONFIG_KEY] = resume_content
    invocation_config = {**config, "configurable": configurable}
    transport = to_orchestration_state(
        state,
        extracted_blocks=tuple(extracted_blocks),
    )
    return graph.invoke(
        _checkpoint_safe_transport(transport),
        config=invocation_config,
    )
