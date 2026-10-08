from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from vikat_hire.contracts import (
    DimensionResolution,
    ExclusionReason,
    ExperienceEvaluation,
    ExperienceRecord,
    ExperienceRequirement,
)

MONTHS_PER_YEAR = Decimal("12")
PERCENTAGE = Decimal("100")
ZERO = Decimal("0")


class ExperienceEvaluationError(ValueError):
    """Raised when deterministic experience evaluation cannot proceed."""


def _month_index(value: date) -> int:
    """
    Convert a date to a monotonic calendar-month index.

    January 2020 -> 2020 * 12 + 0
    February 2020 -> 2020 * 12 + 1
    """
    return value.year * 12 + (value.month - 1)


def _month_start(index: int) -> date:
    """Convert a calendar-month index back to its first day."""
    year, month_zero_based = divmod(index, 12)

    return date(
        year,
        month_zero_based + 1,
        1,
    )


def _month_end(index: int) -> date:
    """Return the final day of a calendar month."""
    start = _month_start(index)

    return date(
        start.year,
        start.month,
        monthrange(start.year, start.month)[1],
    )


def _month_indices(
    start_date: date,
    end_date: date,
) -> range:
    """
    Return every calendar month touched by the inclusive date span.
    """
    start_index = _month_index(start_date)
    end_index = _month_index(end_date)

    if end_index < start_index:
        raise ExperienceEvaluationError(
            "experience end_date cannot precede start_date"
        )

    return range(
        start_index,
        end_index + 1,
    )


def _effective_end_date(
    record: ExperienceRecord,
    as_of_date: date,
) -> date | None:
    """
    Resolve the end date used for deterministic month counting.

    Rules:
    - Explicit end date wins.
    - Current experience uses as_of_date.
    - Missing end date on non-current experience remains unresolved.
    """
    if record.end_date is not None:
        return record.end_date

    if record.current:
        return as_of_date

    return None


def _record_month_indices(
    record: ExperienceRecord,
    as_of_date: date,
) -> tuple[int, ...]:
    """
    Return calendar months represented by one experience record.

    Missing dates do not create artificial dates and therefore contribute
    no months.
    """
    if record.start_date is None:
        return ()

    end_date = _effective_end_date(
        record,
        as_of_date,
    )

    if end_date is None:
        return ()

    if record.start_date > as_of_date:
        return ()

    effective_end = min(
        end_date,
        as_of_date,
    )

    if effective_end < record.start_date:
        return ()

    return tuple(
        _month_indices(
            record.start_date,
            effective_end,
        )
    )


def _record_is_aligned(
    record: ExperienceRecord,
    matched_record_ids: frozenset[str],
) -> bool:
    """
    Determine whether the record has validated JD alignment.

    Alignment is deliberately supplied by the deterministic matching layer;
    this evaluator does not invent semantic alignment.
    """
    return record.record_id in matched_record_ids


def _unique_aligned_months(
    records: tuple[ExperienceRecord, ...],
    matched_record_ids: frozenset[str],
    as_of_date: date,
) -> tuple[set[int], tuple[str, ...]]:
    """
    Build the unique calendar-month set.

    A month can be represented by multiple records but is counted once.
    """
    months: set[int] = set()
    contributing_records: list[str] = []

    for record in records:
        if not _record_is_aligned(
            record,
            matched_record_ids,
        ):
            continue

        record_months = _record_month_indices(
            record,
            as_of_date,
        )

        if not record_months:
            continue

        contributing_records.append(record.record_id)
        months.update(record_months)

    return (
        months,
        tuple(dict.fromkeys(contributing_records)),
    )


def _raw_score(
    aligned_months: int,
    required_years: Decimal,
) -> Decimal:
    """
    Convert aligned calendar months into the 0-100 raw dimension value.

    The value is capped at 100 because exceeding the JD requirement does not
    create more than full coverage.
    """
    if required_years <= ZERO:
        raise ExperienceEvaluationError(
            "required_years must be positive"
        )

    aligned_years = (
        Decimal(aligned_months) / MONTHS_PER_YEAR
    )

    normalized = aligned_years / required_years

    capped = min(
        normalized,
        Decimal("1"),
    )

    return (
        capped * PERCENTAGE
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def evaluate_jd_aligned_experience(
    *,
    records: tuple[ExperienceRecord, ...],
    requirement: ExperienceRequirement,
    matched_record_ids: frozenset[str],
    as_of_date: date,
) -> ExperienceEvaluation:
    """
    Deterministically evaluate JD-aligned candidate experience.

    `matched_record_ids` must come from an upstream validated deterministic
    alignment process. This function does not perform semantic matching.

    The function never applies the 20% scoring weight from
    verifyhire-scoring@2.2.0.
    """
    if as_of_date is None:
        raise ExperienceEvaluationError(
            "as_of_date is required"
        )

    record_ids = [
        record.record_id
        for record in records
    ]

    if len(record_ids) != len(set(record_ids)):
        raise ExperienceEvaluationError(
            "duplicate experience record_id values are not allowed"
        )

    known_record_ids = frozenset(record_ids)

    unknown_matches = matched_record_ids - known_record_ids

    if unknown_matches:
        unknown = ", ".join(sorted(unknown_matches))

        raise ExperienceEvaluationError(
            f"matched_record_ids contain unknown records: {unknown}"
        )

    required_years = requirement.minimum_years

    if required_years is None:
        return ExperienceEvaluation(
            requirement_id=requirement.requirement_id,
            resolution=DimensionResolution.EXCLUDED,
            aligned_months=0,
            contributing_record_ids=(),
            excluded_record_ids=tuple(record_ids),
            evidence_refs=(),
            provenance_refs=requirement.provenance_refs,
            exclusion_reason=ExclusionReason.NOT_APPLICABLE,
            rationale=(
                "The JD does not specify a minimum experience requirement."
            ),
        )

    if required_years <= ZERO:
        raise ExperienceEvaluationError(
            "experience requirement minimum_years must be positive"
        )

    aligned_months_set, contributing_record_ids = (
        _unique_aligned_months(
            records,
            matched_record_ids,
            as_of_date,
        )
    )

    aligned_months = len(aligned_months_set)

    aligned_years = (
        Decimal(aligned_months) / MONTHS_PER_YEAR
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    raw_value = _raw_score(
        aligned_months,
        required_years,
    )

    contributing_records = {
        record_id
        for record_id in contributing_record_ids
    }

    excluded_record_ids = tuple(
        record.record_id
        for record in records
        if record.record_id not in contributing_records
    )

    evidence_refs = tuple(
        dict.fromkeys(
            evidence_ref
            for record in records
            if record.record_id in matched_record_ids
            for evidence_ref in record.evidence_refs
        )
    )

    provenance_refs = tuple(
        dict.fromkeys(
            (
                *requirement.provenance_refs,
                *(
                    provenance_ref
                    for record in records
                    if record.record_id in matched_record_ids
                    for provenance_ref in record.provenance_refs
                ),
            )
        )
    )

    rationale = (
        f"{aligned_months} unique aligned calendar months "
        f"({aligned_years} years) evaluated against "
        f"{required_years} required years."
    )

    return ExperienceEvaluation(
        requirement_id=requirement.requirement_id,
        resolution=DimensionResolution.EVALUATED,
        aligned_months=aligned_months,
        aligned_years=aligned_years,
        required_years=required_years,
        raw_value=raw_value,
        contributing_record_ids=contributing_record_ids,
        excluded_record_ids=excluded_record_ids,
        evidence_refs=evidence_refs,
        provenance_refs=provenance_refs,
        rationale=rationale,
    )
