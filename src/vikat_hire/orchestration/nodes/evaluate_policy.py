from __future__ import annotations

from collections.abc import Mapping

from vikat_hire.contracts.policy import ReviewRequest
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.policy.evaluator import (
    build_mandatory_gates,
    build_policy_result,
)


class PolicyEvaluationNodeError(ValueError):
    """Raised when policy-node input violates orchestration invariants."""


def evaluate_policy_node(
    state: ScreeningState,
    *,
    field_presence: Mapping[str, bool],
    configuration_ref: str,
    review_requests: tuple[ReviewRequest, ...] = (),
) -> ScreeningState:
    """
    Evaluate mandatory policy gates and policy outcome.

    Policy decisions remain authoritative in policy.evaluator.
    This orchestration node only supplies state and explicitly provided
    policy inputs to the deterministic evaluator.

    The node does not:
    - calculate or modify the score,
    - recalculate dimension values,
    - infer missing field presence,
    - create review requests,
    - determine eligibility independently.
    """

    if not isinstance(state, ScreeningState):
        raise PolicyEvaluationNodeError(
            "state must be a ScreeningState"
        )

    if not configuration_ref.strip():
        raise PolicyEvaluationNodeError(
            "configuration_ref must not be blank"
        )

    if state.evaluation is not None:
        if state.evaluation.screening_id != state.screening_id:
            raise PolicyEvaluationNodeError(
                "evaluation screening_id does not match state screening_id"
            )

    if state.score is not None:
        if state.score.screening_id != state.screening_id:
            raise PolicyEvaluationNodeError(
                "score screening_id does not match state screening_id"
            )

    gates = build_mandatory_gates(
        field_presence=field_presence,
        configuration_ref=configuration_ref,
    )

    policy_result = build_policy_result(
        screening_id=state.screening_id,
        gates=gates,
        evaluation=state.evaluation,
        score=state.score,
        review_requests=review_requests,
        configuration_ref=configuration_ref,
    )

    return state.model_copy(
        update={
            "policy": policy_result,
            "pending_reviews": review_requests,
        }
    )