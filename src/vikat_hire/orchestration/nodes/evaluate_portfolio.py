from __future__ import annotations

from vikat_hire.contracts.common import DimensionName, WorkflowStatus
from vikat_hire.contracts.evaluation import DimensionEvaluation, EvaluationResult
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.portfolio import (
    PortfolioEvaluationError,
    evaluate_portfolio_evidence,
)


class PortfolioEvaluationNodeError(ValueError):
    """Raised when Portfolio-evaluation orchestration input or output is invalid."""


def evaluate_portfolio_node(
    state: ScreeningState,
    *,
    requirements: tuple[JDRequirement, ...],
) -> ScreeningState:
    """
    Accumulate the authoritative JD-to-Portfolio dimension without final assembly.

    Requirements are explicit because ScreeningState does not store them.
    The evaluator receives the state's deterministic keyword matches and owns
    Portfolio provenance filtering and raw-value calculation.

    LLM proposals are not inputs.

    This node does not:
    - assemble the final evidence bundle;
    - calculate the final dimension set;
    - calculate scoring weights;
    - calculate the final score;
    - apply policy.
    """

    if not isinstance(state, ScreeningState):
        raise PortfolioEvaluationNodeError(
            "state must be a ScreeningState"
        )

    if state.screening_input.screening_id != state.screening_id:
        raise PortfolioEvaluationNodeError(
            "input screening_id does not match state screening_id"
        )

    if (
        state.status is WorkflowStatus.WAITING_FOR_INPUT
        or state.required_inputs_missing
    ):
        raise PortfolioEvaluationNodeError(
            "required input must be resolved before Portfolio evaluation"
        )

    if state.status is WorkflowStatus.FAILED:
        raise PortfolioEvaluationNodeError(
            "cannot evaluate Portfolio evidence for a failed screening"
        )

    if state.evaluation is not None:
        if state.evaluation.screening_id != state.screening_id:
            raise PortfolioEvaluationNodeError(
                "evaluation screening_id does not match state screening_id"
            )

        if any(
            item.dimension is DimensionName.PORTFOLIO_EVIDENCE
            for item in state.evaluation.dimensions
        ):
            raise PortfolioEvaluationNodeError(
                "Portfolio dimension already exists in evaluation"
            )

    if not isinstance(requirements, tuple) or any(
        not isinstance(requirement, JDRequirement)
        for requirement in requirements
    ):
        raise PortfolioEvaluationNodeError(
            "requirements must be a tuple of JDRequirement objects"
        )

    try:
        dimension = evaluate_portfolio_evidence(
            requirements=requirements,
            claims=state.claims,
            matches=state.keyword_matches,
            provenances=state.provenances,
        )
    except PortfolioEvaluationError as exc:
        raise PortfolioEvaluationNodeError(str(exc)) from exc

    if not isinstance(dimension, DimensionEvaluation):
        raise PortfolioEvaluationNodeError(
            "Portfolio evaluator must return a DimensionEvaluation"
        )

    if dimension.dimension is not DimensionName.PORTFOLIO_EVIDENCE:
        raise PortfolioEvaluationNodeError(
            "Portfolio evaluator must return the PORTFOLIO_EVIDENCE dimension"
        )

    if state.evaluation is None:
        evaluation = EvaluationResult(
            screening_id=state.screening_id,
            dimensions=(dimension,),
            contradiction_refs=(),
            deterministic=True,
        )
    else:
        evaluation = state.evaluation.model_copy(
            update={
                "dimensions": (
                    *state.evaluation.dimensions,
                    dimension,
                ),
            }
        )

    return state.model_copy(
        update={
            "evaluation": evaluation,
        }
    )