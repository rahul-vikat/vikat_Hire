from __future__ import annotations

from vikat_hire.config import get_scoring_configuration
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.scoring import calculate_score


class ScoreCalculationNodeError(ValueError):
    """Raised when score-calculation node input is invalid."""


def calculate_score_node(
    state: ScreeningState,
    *,
    scoring_release: str,
) -> ScreeningState:
    """
    Calculate and attach the authoritative screening score.

    The node delegates all scoring logic to the deterministic scoring
    calculator. It does not calculate weights, normalize values, decide
    applicability, or otherwise modify the EvaluationResult.
    """

    if not isinstance(state, ScreeningState):
        raise ScoreCalculationNodeError(
            "state must be a ScreeningState"
        )

    if not scoring_release.strip():
        raise ScoreCalculationNodeError(
            "scoring_release must not be blank"
        )

    if state.evaluation is None:
        raise ScoreCalculationNodeError(
            "score calculation requires completed evaluation"
        )

    if state.evaluation.screening_id != state.screening_id:
        raise ScoreCalculationNodeError(
            "evaluation screening_id does not match state screening_id"
        )

    configuration = get_scoring_configuration(scoring_release)

    score_result = calculate_score(
        screening_id=state.screening_id,
        evaluations=state.evaluation.dimensions,
        configuration=configuration,
    )

    return state.model_copy(
        update={
            "score": score_result,
        }
    )