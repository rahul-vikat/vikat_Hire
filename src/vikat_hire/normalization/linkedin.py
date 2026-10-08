from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import ValidationError

from vikat_hire.contracts.common import DatePrecision, SourceType
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    NormalizedExperienceRecord,
)


class LinkedInNormalizationError(ValueError):
    """Raised when structured LinkedIn content cannot be normalized."""


def normalize_linkedin_experience(
    *,
    block: ExtractedTextBlock,
) -> tuple[NormalizedExperienceRecord, ...]:
    """Normalize factual employment entries from a LinkedIn JSON object.

    This parser does not match JD requirements, calculate durations, infer
    skills or responsibilities, classify seniority, or score candidates.
    """
    if not isinstance(block, ExtractedTextBlock):
        raise LinkedInNormalizationError(
            "block must be an ExtractedTextBlock"
        )
    if block.source_type is not SourceType.LINKEDIN:
        raise LinkedInNormalizationError(
            "LinkedIn normalization requires a LinkedIn extracted block"
        )

    payload = _parse_payload(block.text)
    if "experience" not in payload:
        raise LinkedInNormalizationError(
            "LinkedIn payload is missing required 'experience' field"
        )
    experience = payload["experience"]
    if not isinstance(experience, list):
        raise LinkedInNormalizationError(
            "LinkedIn payload 'experience' must be a list"
        )

    return tuple(
        _normalize_experience_record(
            raw_record=raw_record,
            block=block,
            index=index,
        )
        for index, raw_record in enumerate(experience)
    )


def _parse_payload(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise LinkedInNormalizationError(
            "LinkedIn extracted content must be text"
        )
    if not text.strip():
        raise LinkedInNormalizationError(
            "LinkedIn extracted content must not be blank"
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LinkedInNormalizationError(
            f"LinkedIn payload is not valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise LinkedInNormalizationError(
            "LinkedIn payload must be a JSON object"
        )
    return payload


def _normalize_experience_record(
    *,
    raw_record: Any,
    block: ExtractedTextBlock,
    index: int,
) -> NormalizedExperienceRecord:
    if not isinstance(raw_record, dict):
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}] must be an object"
        )

    position = _optional_text(raw_record, "position", index=index)
    company = _optional_text(raw_record, "companyName", index=index)
    description = _optional_text(raw_record, "description", index=index)
    start_date, start_precision = _parse_date_field(
        raw_record.get("startDate"),
        field_name="startDate",
        index=index,
    )
    end_date, end_precision, current = _parse_end_date(
        raw_record.get("endDate"),
        index=index,
    )

    try:
        return NormalizedExperienceRecord(
            record_id=f"{block.block_id}:experience:{index}",
            employer=company,
            role=position,
            start_date=start_date,
            end_date=end_date,
            date_precision=_resolve_date_precision(
                start_precision=start_precision,
                end_precision=end_precision,
            ),
            current=current,
            skill_refs=(),
            responsibility_refs=(),
            source_text=_source_text(
                raw_record=raw_record,
                description=description,
            ),
            source_type=SourceType.LINKEDIN,
            source_ref=block.source_ref,
            evidence_refs=(block.block_id,),
            provenance_refs=block.provenance_refs,
        )
    except ValidationError as exc:
        raise LinkedInNormalizationError(
            f"invalid normalized LinkedIn experience[{index}]: {exc}"
        ) from exc


def _optional_text(
    record: dict[str, Any],
    field_name: str,
    *,
    index: int,
) -> str | None:
    value = record.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].{field_name} "
            "must be a string or null"
        )
    return value.strip() or None


def _parse_date_field(
    value: Any,
    *,
    field_name: str,
    index: int,
) -> tuple[date | None, DatePrecision]:
    if value is None:
        return None, DatePrecision.UNKNOWN
    if not isinstance(value, dict):
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].{field_name} "
            "must be an object or null"
        )

    month = value.get("month")
    year = value.get("year")
    if month is None and year is None:
        return None, DatePrecision.UNKNOWN
    if year is None:
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].{field_name} "
            "contains month without year"
        )
    if not isinstance(year, int) or isinstance(year, bool):
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].{field_name}.year "
            "must be an integer"
        )
    if year < 1:
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].{field_name}.year "
            "must be positive"
        )
    if month is None:
        return _validated_date(year, 1, field_name=field_name, index=index), DatePrecision.YEAR
    if not isinstance(month, int) or isinstance(month, bool):
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].{field_name}.month "
            "must be an integer"
        )
    if month < 1 or month > 12:
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].{field_name}.month "
            "must be between 1 and 12"
        )
    return (
        _validated_date(year, month, field_name=field_name, index=index),
        DatePrecision.MONTH,
    )


def _validated_date(
    year: int,
    month: int,
    *,
    field_name: str,
    index: int,
) -> date:
    try:
        return date(year, month, 1)
    except ValueError as exc:
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].{field_name} contains an invalid date"
        ) from exc


def _parse_end_date(
    value: Any,
    *,
    index: int,
) -> tuple[date | None, DatePrecision, bool]:
    if value is None:
        return None, DatePrecision.UNKNOWN, False
    if not isinstance(value, dict):
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].endDate must be an object or null"
        )

    text = value.get("text")
    if text is not None and not isinstance(text, str):
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].endDate.text "
            "must be a string or null"
        )
    normalized_text = text.strip().lower() if isinstance(text, str) else None
    has_explicit_date = value.get("month") is not None or value.get("year") is not None
    is_present = normalized_text == "present"
    if is_present and has_explicit_date:
        raise LinkedInNormalizationError(
            f"LinkedIn experience[{index}].endDate cannot contain both "
            "Present and an explicit date"
        )
    if is_present:
        return None, DatePrecision.UNKNOWN, True

    parsed_date, precision = _parse_date_field(
        value,
        field_name="endDate",
        index=index,
    )
    return parsed_date, precision, False


def _resolve_date_precision(
    *,
    start_precision: DatePrecision,
    end_precision: DatePrecision,
) -> DatePrecision:
    if DatePrecision.MONTH in (start_precision, end_precision):
        return DatePrecision.MONTH
    if DatePrecision.YEAR in (start_precision, end_precision):
        return DatePrecision.YEAR
    return DatePrecision.UNKNOWN


def _source_text(
    *,
    raw_record: dict[str, Any],
    description: str | None,
) -> str:
    if description is not None:
        return description
    return json.dumps(
        raw_record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
