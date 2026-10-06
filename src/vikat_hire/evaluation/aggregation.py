from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal, ROUND_HALF_UP

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


class RequirementAggregationError(ValueError):
    """Raised when requirement aggregation input is invalid."""


_QUANTUM = Decimal("0.01")

_EVALUATED_STATUSES = frozenset(
    {
        MatchStatus.MATCHED,
        MatchStatus.PARTIAL,
        MatchStatus.NOT_MATCHED,
    }
)


def aggregate_requirement_group(
    *,
    importance: RequirementImportance,
    requirement_ids: Iterable[str],
    evaluations: Mapping[str, RequirementEvaluation],
) -> RequirementGroupEvaluation:
    """Aggregate one requirement-importance group deterministically.

    UNRESOLVED requirements are excluded from the denominator.

    MATCHED, PARTIAL, and NOT_MATCHED requirements are evaluated.
    Therefore an evaluated NOT_MATCHED requirement with raw_score=0
    remains part of the denominator.
    """
    ids = tuple(requirement_ids)

    if len(ids) != len(set(ids)):
        raise RequirementAggregationError(
            "duplicate requirement IDs are not allowed"
        )

    if any(
        not isinstance(requirement_id, str) or not requirement_id.strip()
        for requirement_id in ids
    ):
        raise RequirementAggregationError(
            "requirement IDs must be non-empty strings"
        )

    unknown_ids = [
        requirement_id
        for requirement_id in ids
        if requirement_id not in evaluations
    ]

    if unknown_ids:
        raise RequirementAggregationError(
            f"missing evaluations for requirement IDs: {unknown_ids}"
        )

    evaluated_ids = tuple(
        requirement_id
        for requirement_id in ids
        if evaluations[requirement_id].status in _EVALUATED_STATUSES
    )

    excluded_ids = tuple(
        requirement_id
        for requirement_id in ids
        if evaluations[requirement_id].status not in _EVALUATED_STATUSES
    )

    if not evaluated_ids:
        return RequirementGroupEvaluation(
            importance=importance,
            resolution=DimensionResolution.EXCLUDED,
            raw_value=None,
            requirement_ids=ids,
            evaluated_requirement_ids=(),
            excluded_requirement_ids=excluded_ids,
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
        )

    total = sum(
        (
            evaluations[requirement_id].raw_score
            for requirement_id in evaluated_ids
        ),
        Decimal("0"),
    )

    coverage = (
        total / Decimal(len(evaluated_ids))
    ).quantize(
        _QUANTUM,
        rounding=ROUND_HALF_UP,
    )

    return RequirementGroupEvaluation(
        importance=importance,
        resolution=DimensionResolution.EVALUATED,
        raw_value=coverage,
        requirement_ids=ids,
        evaluated_requirement_ids=evaluated_ids,
        excluded_requirement_ids=excluded_ids,
        exclusion_reason=None,
    )


def aggregate_must_have_coverage(
    *,
    requirement_ids: Iterable[str],
    evaluations: Mapping[str, RequirementEvaluation],
) -> RequirementGroupEvaluation:
    return aggregate_requirement_group(
        importance=RequirementImportance.MUST_HAVE,
        requirement_ids=requirement_ids,
        evaluations=evaluations,
    )


def aggregate_nice_to_have_coverage(
    *,
    requirement_ids: Iterable[str],
    evaluations: Mapping[str, RequirementEvaluation],
) -> RequirementGroupEvaluation:
    return aggregate_requirement_group(
        importance=RequirementImportance.NICE_TO_HAVE,
        requirement_ids=requirement_ids,
        evaluations=evaluations,
    )