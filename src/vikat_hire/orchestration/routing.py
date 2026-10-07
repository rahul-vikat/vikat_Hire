from __future__ import annotations

from vikat_hire.contracts.common import WorkflowStatus
from vikat_hire.contracts.state import ScreeningState


TECHNICAL_JD_TYPE = "technical"
NON_TECHNICAL_JD_TYPE = "non_technical"

NODE_VALIDATE_INPUT = "validate_input"
NODE_CLASSIFY_JD = "classify_jd"
NODE_MATCH_KEYWORDS = "match_keywords"
NODE_MATCH_SEMANTIC = "match_semantic"
NODE_EVALUATE_LINKEDIN = "evaluate_linkedin"
NODE_EVALUATE_GITHUB = "evaluate_github"
NODE_EVALUATE_PORTFOLIO = "evaluate_portfolio"
NODE_EVALUATE_DIMENSIONS = "evaluate_dimensions"
NODE_CALCULATE_SCORE = "calculate_score"
NODE_EVALUATE_POLICY = "evaluate_policy"
NODE_GENERATE_EXPLANATION = "generate_explanation"
NODE_END = "end"
NODE_INTERRUPT = "interrupt"
NODE_REVIEW = "review"


class RoutingError(ValueError):
    """Raised when orchestration routing input violates routing invariants."""


def route_after_input_validation(
    state: ScreeningState,
) -> str:
    """
    Route after required-input validation.

    Missing required data must interrupt the workflow rather than being
    silently guessed or skipped.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    if state.required_inputs_missing:
        return NODE_INTERRUPT

    return NODE_CLASSIFY_JD


def route_after_classification(
    state: ScreeningState,
) -> str:
    """
    Route after deterministic JD classification.

    Classification itself is performed by the classification node.
    This function only selects the next graph node.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    if state.classification is None:
        raise RoutingError(
            "classification is required before classification routing"
        )

    jd_type = state.classification.jd_type.strip().lower()

    if jd_type not in {
        TECHNICAL_JD_TYPE,
        NON_TECHNICAL_JD_TYPE,
    }:
        raise RoutingError(
            "unsupported JD classification: "
            f"{state.classification.jd_type!r}"
        )

    return NODE_MATCH_KEYWORDS


def route_after_linkedin(
    state: ScreeningState,
) -> str:
    """
    Route after LinkedIn evidence evaluation.

    LinkedIn evaluation is common to both technical and non-technical
    workflows.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    if state.classification is None:
        raise RoutingError(
            "classification is required before LinkedIn routing"
        )

    return _route_external_evidence(
        state,
        next_common_node=NODE_EVALUATE_DIMENSIONS,
    )


def route_after_semantic_matching(
    state: ScreeningState,
) -> str:
    """
    Route after deterministic/LLM-assisted semantic matching.

    LLM semantic proposals do not determine routing directly.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    if state.classification is None:
        raise RoutingError(
            "classification is required before semantic routing"
        )

    return NODE_EVALUATE_LINKEDIN


def route_after_github(
    state: ScreeningState,
) -> str:
    """
    Route after GitHub evaluation for a technical JD.

    Portfolio evaluation follows GitHub for technical JDs.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    _require_classification(state)

    jd_type = state.classification.jd_type.strip().lower()

    if jd_type != TECHNICAL_JD_TYPE:
        raise RoutingError(
            "GitHub routing is only valid for technical JDs"
        )

    return NODE_EVALUATE_PORTFOLIO


def route_after_portfolio(
    state: ScreeningState,
) -> str:
    """
    Route after Portfolio evaluation.

    Evidence assembly/dimension evaluation follows external evidence.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    _require_classification(state)

    return NODE_EVALUATE_DIMENSIONS


def route_after_dimensions(
    state: ScreeningState,
) -> str:
    """
    Route after deterministic dimension evaluation.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    if state.evaluation is None:
        raise RoutingError(
            "evaluation is required before score routing"
        )

    if state.evaluation.screening_id != state.screening_id:
        raise RoutingError(
            "evaluation screening_id does not match state screening_id"
        )

    return NODE_CALCULATE_SCORE


def route_after_score(
    state: ScreeningState,
) -> str:
    """
    Route after the authoritative 2.2.0 score calculation.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    if state.score is None:
        raise RoutingError(
            "score is required before policy routing"
        )

    if state.score.screening_id != state.screening_id:
        raise RoutingError(
            "score screening_id does not match state screening_id"
        )

    return NODE_EVALUATE_POLICY


def route_after_policy(
    state: ScreeningState,
) -> str:
    """
    Route after deterministic policy evaluation.

    Policy is authoritative for workflow status and eligibility.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    if state.policy is None:
        raise RoutingError(
            "policy result is required before policy routing"
        )

    if state.policy.screening_id != state.screening_id:
        raise RoutingError(
            "policy screening_id does not match state screening_id"
        )

    if state.policy.workflow_status is WorkflowStatus.FAILED:
        return NODE_END

    if state.policy.workflow_status is WorkflowStatus.REVIEW_REQUIRED:
        return NODE_REVIEW

    if state.policy.workflow_status is WorkflowStatus.COMPLETED:
        return NODE_GENERATE_EXPLANATION

    raise RoutingError(
        "unsupported policy workflow status: "
        f"{state.policy.workflow_status.value!r}"
    )


def route_after_review(
    state: ScreeningState,
) -> str:
    """
    Route after a human-review boundary.

    Review completion is represented by the absence of pending reviews.
    The actual review action belongs outside this deterministic router.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    if state.policy is None:
        raise RoutingError(
            "policy result is required before review routing"
        )

    if state.policy.workflow_status is not WorkflowStatus.REVIEW_REQUIRED:
        raise RoutingError(
            "review routing requires policy workflow status "
            "REVIEW_REQUIRED"
        )

    if state.pending_reviews:
        return NODE_REVIEW

    return NODE_GENERATE_EXPLANATION


def route_after_explanation(
    state: ScreeningState,
) -> str:
    """
    Route after explanation generation.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    if state.explanation is None:
        raise RoutingError(
            "explanation is required before final routing"
        )

    if state.explanation.screening_id != state.screening_id:
        raise RoutingError(
            "explanation screening_id does not match state screening_id"
        )

    return NODE_END


def route_after_matching(
    state: ScreeningState,
) -> str:
    """
    Route after keyword/semantic matching.

    Technical classification controls whether GitHub and Portfolio
    evaluation is activated.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    _require_classification(state)

    return NODE_EVALUATE_LINKEDIN


def route_after_linkedin_evidence(
    state: ScreeningState,
) -> str:
    """
    Route from LinkedIn evidence into technical/non-technical branching.

    Technical JDs activate GitHub and Portfolio evaluation.
    Non-technical JDs skip both and continue to dimension evaluation.
    """

    if not isinstance(state, ScreeningState):
        raise RoutingError("state must be a ScreeningState")

    _require_classification(state)

    jd_type = state.classification.jd_type.strip().lower()

    if jd_type == TECHNICAL_JD_TYPE:
        return NODE_EVALUATE_GITHUB

    if jd_type == NON_TECHNICAL_JD_TYPE:
        return NODE_EVALUATE_DIMENSIONS

    raise RoutingError(
        "unsupported JD classification: "
        f"{state.classification.jd_type!r}"
    )


def _route_external_evidence(
    state: ScreeningState,
    *,
    next_common_node: str,
) -> str:
    _require_classification(state)

    if not next_common_node.strip():
        raise RoutingError(
            "next_common_node must not be blank"
        )

    return next_common_node


def _require_classification(
    state: ScreeningState,
) -> None:
    if state.classification is None:
        raise RoutingError(
            "classification is required for routing"
        )

    if not state.classification.jd_type.strip():
        raise RoutingError(
            "classification jd_type must not be blank"
        )