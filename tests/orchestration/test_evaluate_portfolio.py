from decimal import Decimal
from importlib import import_module

import pytest

from vikat_hire.contracts.common import (
    AccessStatus,
    ApplicabilityStatus,
    DerivationMethod,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    InputKind,
    MatchStatus,
    Provenance,
    RequirementCategory,
    RequirementImportance,
    SourceType,
    WorkflowStatus,
)
from vikat_hire.contracts.evaluation import DimensionEvaluation, EvaluationResult
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.matching import KeywordMatch
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.portfolio import (
    PortfolioEvaluationError,
    evaluate_portfolio_evidence,
)
from vikat_hire.orchestration.nodes.evaluate_portfolio import (
    PortfolioEvaluationNodeError,
    evaluate_portfolio_node,
)


NODE_MODULE = import_module(
    "vikat_hire.orchestration.nodes.evaluate_portfolio"
)


@pytest.fixture
def portfolio_input():
    requirements = tuple(
        JDRequirement(
            requirement_id=name,
            text=name,
            category=RequirementCategory.SKILL,
            importance=RequirementImportance.MUST_HAVE,
            source_type=SourceType.JD_FILE,
            source_ref="jd-1",
            evidence_refs=("jd-evidence",),
            provenance_refs=("jd-prov",),
        )
        for name in (
            "Python",
            "FastAPI",
            "Docker",
            "Kubernetes",
        )
    )

    documents = {
        kind.value: DocumentInput(
            input_id=f"{kind.value}-1",
            kind=kind,
            filename=f"{kind.value}.txt",
            media_type="text/plain",
            content_hash="hash",
            storage_ref=f"storage/{kind.value}",
        )
        for kind in (
            InputKind.JD,
            InputKind.RESUME,
        )
    }

    provenance = Provenance(
        provenance_id="portfolio-prov",
        source_type=SourceType.PORTFOLIO,
        source_ref="portfolio-source",
        method=DerivationMethod.CRAWLER,
        access_status=AccessStatus.AUTHORIZED,
    )

    claims = tuple(
        Claim(
            claim_id=f"claim-{req.requirement_id}",
            subject="portfolio",
            predicate="demonstrates",
            value=req.text,
            provenance_refs=("portfolio-prov",),
        )
        for req in requirements[:3]
    )

    matches = tuple(
        KeywordMatch(
            match_id=f"match-{req.requirement_id}",
            requirement_id=req.requirement_id,
            candidate_claim_id=claim.claim_id,
            match_type="portfolio_requirement_match",
            status=status,
            score=Decimal(score),
            provenance_refs=("portfolio-prov",),
        )
        for req, claim, status, score in zip(
            requirements,
            claims,
            (
                MatchStatus.MATCHED,
                MatchStatus.PARTIAL,
                MatchStatus.NOT_MATCHED,
            ),
            (
                "100",
                "70",
                "0",
            ),
        )
    )

    state = ScreeningState(
        screening_id="screening-1",
        screening_input=ScreeningInput(
            screening_id="screening-1",
            **documents,
        ),
        claims=claims,
        provenances=(provenance,),
        keyword_matches=matches,
        current_node="evaluate_portfolio",
        revision=7,
        errors=("existing diagnostic",),
    )

    return state, requirements


def _dimension(
    name=DimensionName.LINKEDIN_EVIDENCE,
):
    return DimensionEvaluation(
        dimension=name,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("81.23"),
        evidence_refs=("evidence-1",),
        provenance_refs=("provenance-1",),
        rationale="Existing result",
    )


def test_success_delegates_raw_score_and_preserves_state(
    portfolio_input,
):
    state, requirements = portfolio_input

    expected = evaluate_portfolio_evidence(
        requirements=requirements,
        claims=state.claims,
        matches=state.keyword_matches,
        provenances=state.provenances,
    )

    result = evaluate_portfolio_node(
        state,
        requirements=requirements,
    )

    dimension = result.evaluation.dimensions[0]

    assert dimension.dimension is DimensionName.PORTFOLIO_EVIDENCE
    assert dimension.raw_value == Decimal("56.67")

    assert (
        dimension.model_dump(
            exclude={"dimension_id", "created_at"}
        )
        == expected.model_dump(
            exclude={"dimension_id", "created_at"}
        )
    )

    assert state.evaluation is None
    assert result.evaluation.screening_id == state.screening_id

    for field in ScreeningState.model_fields:
        if field != "evaluation":
            assert getattr(result, field) == getattr(state, field)


def test_preserves_prior_dimensions_contradictions_and_evaluation_metadata(
    portfolio_input,
):
    state, requirements = portfolio_input

    existing = EvaluationResult(
        screening_id=state.screening_id,
        dimensions=(
            _dimension(),
            _dimension(DimensionName.MUST_HAVE_COVERAGE),
        ),
        contradiction_refs=(
            "contradiction-2",
            "contradiction-1",
        ),
    )

    state = state.model_copy(
        update={
            "evaluation": existing,
        }
    )

    result = evaluate_portfolio_node(
        state,
        requirements=requirements,
    )

    assert result.evaluation.dimensions[:-1] == existing.dimensions
    assert result.evaluation.dimensions[0] is existing.dimensions[0]
    assert (
        result.evaluation.contradiction_refs
        == existing.contradiction_refs
    )
    assert result.evaluation.created_at == existing.created_at
    assert result.evaluation.deterministic == existing.deterministic
    assert state.evaluation is existing


@pytest.mark.parametrize("count", [1, 2])
def test_existing_portfolio_dimension_is_rejected_before_evaluator(
    portfolio_input,
    monkeypatch,
    count,
):
    state, requirements = portfolio_input

    state = state.model_copy(
        update={
            "evaluation": EvaluationResult(
                screening_id=state.screening_id,
                dimensions=(
                    _dimension(DimensionName.PORTFOLIO_EVIDENCE),
                )
                * count,
            )
        }
    )

    monkeypatch.setattr(
        NODE_MODULE,
        "evaluate_portfolio_evidence",
        lambda **kwargs: pytest.fail("called"),
    )

    with pytest.raises(
        PortfolioEvaluationNodeError,
        match="already exists",
    ):
        evaluate_portfolio_node(
            state,
            requirements=requirements,
        )


@pytest.mark.parametrize(
    "problem",
    [
        "input_identity",
        "evaluation_identity",
        "waiting",
        "missing",
        "failed",
    ],
)
def test_invalid_prerequisites_fail_before_evaluator(
    portfolio_input,
    monkeypatch,
    problem,
):
    state, requirements = portfolio_input

    changes = {
        "input_identity": {
            "screening_input": state.screening_input.model_copy(
                update={"screening_id": "other"}
            )
        },
        "evaluation_identity": {
            "evaluation": EvaluationResult(
                screening_id="other",
                dimensions=(),
            )
        },
        "waiting": {
            "status": WorkflowStatus.WAITING_FOR_INPUT,
        },
        "missing": {
            "required_inputs_missing": (
                "jd.extracted_content",
            ),
        },
        "failed": {
            "status": WorkflowStatus.FAILED,
        },
    }

    monkeypatch.setattr(
        NODE_MODULE,
        "evaluate_portfolio_evidence",
        lambda **kwargs: pytest.fail("called"),
    )

    with pytest.raises(PortfolioEvaluationNodeError):
        evaluate_portfolio_node(
            state.model_copy(update=changes[problem]),
            requirements=requirements,
        )


@pytest.mark.parametrize(
    "state",
    [
        None,
        "invalid",
        {},
    ],
)
def test_invalid_state_rejected(state):
    with pytest.raises(
        PortfolioEvaluationNodeError,
        match="state must be a ScreeningState",
    ):
        evaluate_portfolio_node(
            state,
            requirements=(),
        )


@pytest.mark.parametrize(
    "requirements",
    [
        None,
        ("bad",),
        [],
    ],
)
def test_invalid_requirements_rejected(
    portfolio_input,
    requirements,
):
    with pytest.raises(
        PortfolioEvaluationNodeError,
        match="tuple of JDRequirement",
    ):
        evaluate_portfolio_node(
            portfolio_input[0],
            requirements=requirements,
        )


def test_evaluator_error_is_translated_with_cause(
    portfolio_input,
):
    state, requirements = portfolio_input

    with pytest.raises(
        PortfolioEvaluationNodeError,
        match="duplicate JD requirement",
    ) as raised:
        evaluate_portfolio_node(
            state,
            requirements=(
                *requirements,
                requirements[0],
            ),
        )

    assert isinstance(
        raised.value.__cause__,
        PortfolioEvaluationError,
    )


@pytest.mark.parametrize(
    "output",
    [
        None,
        "invalid",
        _dimension(),
    ],
)
def test_invalid_return_type_or_dimension_rejected(
    portfolio_input,
    monkeypatch,
    output,
):
    monkeypatch.setattr(
        NODE_MODULE,
        "evaluate_portfolio_evidence",
        lambda **kwargs: output,
    )

    with pytest.raises(
        PortfolioEvaluationNodeError,
        match="Portfolio evaluator must return",
    ):
        evaluate_portfolio_node(
            portfolio_input[0],
            requirements=portfolio_input[1],
        )


@pytest.mark.parametrize(
    "no_provenance",
    [
        False,
        True,
    ],
)
def test_excluded_result_stays_excluded(
    portfolio_input,
    no_provenance,
):
    state, requirements = portfolio_input

    state = state.model_copy(
        update={
            "claims": (),
            "keyword_matches": (),
            "provenances": (
                ()
                if no_provenance
                else state.provenances
            ),
        }
    )

    # Normalize the tuple assignment above for the no-provenance case.
    if no_provenance:
        state = state.model_copy(
            update={"provenances": ()}
        )

    result = evaluate_portfolio_node(
        state,
        requirements=requirements,
    )

    dimension = result.evaluation.dimensions[0]

    assert dimension.resolution is DimensionResolution.EXCLUDED
    assert dimension.raw_value is None

    assert dimension.exclusion_reason is (
        ExclusionReason.NOT_FOUND
        if no_provenance
        else ExclusionReason.INSUFFICIENT_EVIDENCE
    )


def test_exact_evaluator_artifact_and_arguments_are_preserved(
    portfolio_input,
    monkeypatch,
):
    state, requirements = portfolio_input

    dimension = DimensionEvaluation(
        dimension=DimensionName.PORTFOLIO_EVIDENCE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EXCLUDED,
        exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
        evidence_refs=("evidence-x",),
        provenance_refs=("provenance-x",),
        requirement_refs=("requirement-x",),
        rationale="Unresolved",
    )

    def evaluator(**kwargs):
        assert kwargs == {
            "requirements": requirements,
            "claims": state.claims,
            "matches": state.keyword_matches,
            "provenances": state.provenances,
        }

        return dimension

    monkeypatch.setattr(
        NODE_MODULE,
        "evaluate_portfolio_evidence",
        evaluator,
    )

    result = evaluate_portfolio_node(
        state,
        requirements=requirements,
    )

    assert (
        result.evaluation.dimensions[0]
        is dimension
    )


def test_unexpected_failure_propagates(
    portfolio_input,
    monkeypatch,
):
    error = RuntimeError("unexpected failure")

    def evaluator(**kwargs):
        raise error

    monkeypatch.setattr(
        NODE_MODULE,
        "evaluate_portfolio_evidence",
        evaluator,
    )

    with pytest.raises(RuntimeError) as raised:
        evaluate_portfolio_node(
            portfolio_input[0],
            requirements=portfolio_input[1],
        )

    assert raised.value is error