from __future__ import annotations

from vikat_hire.contracts.common import DimensionName, WorkflowStatus
from vikat_hire.contracts.evaluation import DimensionEvaluation, EvaluationResult
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.github_match import (
    GitHubEvaluationError,
    evaluate_github_evidence,
)


class GitHubEvaluationNodeError(ValueError):
    """Raised when GitHub-evaluation orchestration input or output is invalid."""


def evaluate_github_node(
    state: ScreeningState,
    *,
    requirements: tuple[JDRequirement, ...],
) -> ScreeningState:
    """Accumulate the authoritative JD-to-GitHub dimension without final assembly.

    Requirements are explicit because ScreeningState does not store them. The
    evaluator receives the state's deterministic keyword matches and owns GitHub
    provenance filtering and raw-value calculation. LLM proposals are not inputs.

    As with the existing LinkedIn adapter, state.evaluation holds intermediate
    dimensions. Evidence Assembly must still precede final Dimension Evaluation;
    this node neither assembles the final evaluation nor calculates a score.
    """
    if not isinstance(state, ScreeningState):
        raise GitHubEvaluationNodeError("state must be a ScreeningState")
    if state.screening_input.screening_id != state.screening_id:
        raise GitHubEvaluationNodeError("input screening_id does not match state screening_id")
    if state.status is WorkflowStatus.WAITING_FOR_INPUT or state.required_inputs_missing:
        raise GitHubEvaluationNodeError("required input must be resolved before GitHub evaluation")
    if state.status is WorkflowStatus.FAILED:
        raise GitHubEvaluationNodeError("cannot evaluate GitHub evidence for a failed screening")
    if state.evaluation is not None:
        if state.evaluation.screening_id != state.screening_id:
            raise GitHubEvaluationNodeError(
                "evaluation screening_id does not match state screening_id"
            )
        if any(
            item.dimension is DimensionName.GITHUB_EVIDENCE for item in state.evaluation.dimensions
        ):
            raise GitHubEvaluationNodeError("GitHub dimension already exists in evaluation")
    if not isinstance(requirements, tuple) or any(
        not isinstance(requirement, JDRequirement) for requirement in requirements
    ):
        raise GitHubEvaluationNodeError("requirements must be a tuple of JDRequirement objects")

    try:
        dimension = evaluate_github_evidence(
            requirements=requirements,
            claims=state.claims,
            matches=state.keyword_matches,
            provenances=state.provenances,
        )
    except GitHubEvaluationError as exc:
        raise GitHubEvaluationNodeError(str(exc)) from exc

    if not isinstance(dimension, DimensionEvaluation):
        raise GitHubEvaluationNodeError("GitHub evaluator must return a DimensionEvaluation")
    if dimension.dimension is not DimensionName.GITHUB_EVIDENCE:
        raise GitHubEvaluationNodeError(
            "GitHub evaluator must return the GITHUB_EVIDENCE dimension"
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
                "dimensions": (*state.evaluation.dimensions, dimension),
            }
        )
    return state.model_copy(update={"evaluation": evaluation})
