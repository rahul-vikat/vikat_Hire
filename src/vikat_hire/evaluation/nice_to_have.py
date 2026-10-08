from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from vikat_hire.contracts.common import (
    DimensionResolution,
    ExclusionReason,
    MatchStatus,
    RequirementImportance,
)
from vikat_hire.contracts.evaluation import (
    RequirementEvaluation,
    RequirementGroupEvaluation,
)


class NiceToHaveEvaluationError(ValueError):
    """Raised when nice-to-have aggregation input is invalid."""


_QUANTUM = Decimal("0.01")


def evaluate_nice_to_have(
    *,
    evaluations: tuple[RequirementEvaluation, ...],
) -> RequirementGroupEvaluation:
    """
    Aggregate deterministic evaluations for the NICE_TO_HAVE group.

    Rules:
    - MATCHED, PARTIAL, and NOT_MATCHED requirements are evaluable.
    - UNRESOLVED requirements are excluded from the denominator.
    - NOT_MATCHED is a real zero and remains in the denominator.
    - At least one evaluable requirement produces an arithmetic mean.
    - If all requirements are unresolved, the group is EXCLUDED.
    - Values are rounded deterministically to two decimal places.
    """

    _validate_inputs(evaluations)

    ordered_evaluations = tuple(
        sorted(
            evaluations,
            key=lambda evaluation: evaluation.requirement_id,
        )
    )

    requirement_ids = tuple(
        evaluation.requirement_id
        for evaluation in ordered_evaluations
    )

    evaluated = tuple(
        evaluation
        for evaluation in ordered_evaluations
        if evaluation.status is not MatchStatus.UNRESOLVED
    )

    excluded = tuple(
        evaluation
        for evaluation in ordered_evaluations
        if evaluation.status is MatchStatus.UNRESOLVED
    )

    if not evaluated:
        return RequirementGroupEvaluation(
            importance=RequirementImportance.NICE_TO_HAVE,
            resolution=DimensionResolution.EXCLUDED,
            requirement_ids=requirement_ids,
            evaluated_requirement_ids=(),
            excluded_requirement_ids=tuple(
                evaluation.requirement_id
                for evaluation in excluded
            ),
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
        )

    total = sum(
        (
            evaluation.raw_score
            for evaluation in evaluated
        ),
        Decimal("0"),
    )

    raw_value = (
        total / Decimal(len(evaluated))
    ).quantize(
        _QUANTUM,
        rounding=ROUND_HALF_UP,
    )

    return RequirementGroupEvaluation(
        importance=RequirementImportance.NICE_TO_HAVE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=raw_value,
        requirement_ids=requirement_ids,
        evaluated_requirement_ids=tuple(
            evaluation.requirement_id
            for evaluation in evaluated
        ),
        excluded_requirement_ids=tuple(
            evaluation.requirement_id
            for evaluation in excluded
        ),
    )


def _validate_inputs(
    evaluations: tuple[RequirementEvaluation, ...],
) -> None:
    requirement_ids = tuple(
        evaluation.requirement_id
        for evaluation in evaluations
    )

    if len(requirement_ids) != len(set(requirement_ids)):
        raise NiceToHaveEvaluationError(
            "duplicate requirement evaluations are not allowed"
        )

    if any(
        not requirement_id.strip()
        for requirement_id in requirement_ids
    ):
        raise NiceToHaveEvaluationError(
            "requirement evaluation IDs must not be blank"
        )