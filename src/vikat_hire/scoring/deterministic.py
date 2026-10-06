from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from vikat_hire.config import ImmutableScoringConfiguration
from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
)
from vikat_hire.contracts.evaluation import DimensionEvaluation
from vikat_hire.contracts.scoring import (
    DimensionScore,
    ScoreAudit,
    ScoreResult,
)


_SCORE_QUANTUM = Decimal("0.01")
_HUNDRED = Decimal("100")


class DeterministicScoringError(ValueError):
    """Raised when scoring input violates deterministic scoring rules."""


def calculate_score(
    *,
    screening_id: str,
    evaluations: tuple[DimensionEvaluation, ...],
    configuration: ImmutableScoringConfiguration,
) -> ScoreResult:
    """
    Calculate the 2.2.0 applicability-renormalized weighted score.

    Formula:

        score =
            Σ(weight_i × normalized_value_i)
            / Σ(weight_i)

    where:

        normalized_value_i = raw_value_i / 100

    Only APPLICABLE + EVALUATED dimensions participate.
    """

    _validate_evaluations(evaluations)

    dimension_scores: list[DimensionScore] = []
    audits: list[ScoreAudit] = []

    weighted_numerator = Decimal("0")
    applicable_weight_total = Decimal("0")

    for evaluation in evaluations:
        weight = configuration.weight_for(evaluation.dimension)

        if not _is_scored(evaluation):
            dimension_scores.append(
                DimensionScore(
                    dimension=evaluation.dimension,
                    resolution=DimensionResolution.EXCLUDED,
                    weight=weight,
                    raw_value=None,
                    normalized_value=None,
                    weighted_contribution=Decimal("0"),
                    evidence_refs=evaluation.evidence_refs,
                )
            )
            continue

        assert evaluation.raw_value is not None

        normalized_value = evaluation.raw_value / _HUNDRED

        weighted_contribution = weight * normalized_value

        weighted_numerator += weighted_contribution
        applicable_weight_total += weight

        dimension_scores.append(
            DimensionScore(
                dimension=evaluation.dimension,
                resolution=DimensionResolution.EVALUATED,
                weight=weight,
                raw_value=evaluation.raw_value,
                normalized_value=normalized_value,
                weighted_contribution=weighted_contribution,
                evidence_refs=evaluation.evidence_refs,
            )
        )

        audits.append(
            ScoreAudit(
                dimension=evaluation.dimension,
                input_evaluation_ref=evaluation.dimension_id,
                evidence_refs=evaluation.evidence_refs,
                configuration_ref=configuration.release.release,
                weight=weight,
                normalized_value=normalized_value,
                weighted_contribution=weighted_contribution,
            )
        )

    score = _final_score(
        weighted_numerator=weighted_numerator,
        applicable_weight_total=applicable_weight_total,
    )

    return ScoreResult(
        screening_id=screening_id,
        dimensions=tuple(dimension_scores),
        applicable_weight_total=applicable_weight_total,
        score=score,
        audit=tuple(audits),
    )


def _is_scored(evaluation: DimensionEvaluation) -> bool:
    return (
        evaluation.applicability is ApplicabilityStatus.APPLICABLE
        and evaluation.resolution is DimensionResolution.EVALUATED
    )


def _final_score(
    *,
    weighted_numerator: Decimal,
    applicable_weight_total: Decimal,
) -> Decimal | None:
    if applicable_weight_total == Decimal("0"):
        return None

    score = (
        weighted_numerator
        / (applicable_weight_total / _HUNDRED)
    )

    return score.quantize(
        _SCORE_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def _validate_evaluations(
    evaluations: tuple[DimensionEvaluation, ...],
) -> None:
    seen: set[DimensionName] = set()

    for evaluation in evaluations:
        if evaluation.dimension in seen:
            raise DeterministicScoringError(
                "duplicate dimension evaluation: "
                f"{evaluation.dimension.value}"
            )

        seen.add(evaluation.dimension)

        is_scored = _is_scored(evaluation)

        if is_scored and evaluation.raw_value is None:
            raise DeterministicScoringError(
                "applicable/evaluated dimension must have raw_value: "
                f"{evaluation.dimension.value}"
            )

        if not is_scored and evaluation.raw_value is not None:
            raise DeterministicScoringError(
                "excluded dimension must not have raw_value: "
                f"{evaluation.dimension.value}"
            )