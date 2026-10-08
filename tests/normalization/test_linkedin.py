from __future__ import annotations

import json

import pytest

from vikat_hire.contracts.common import DatePrecision, SourceType
from vikat_hire.contracts.normalization import ExtractedTextBlock, ExtractionKind
from vikat_hire.normalization.linkedin import (
    LinkedInNormalizationError,
    normalize_linkedin_experience,
)


def _block(
    payload: dict,
    *,
    block_id: str = "linkedin-block-001",
    source_ref: str = "linkedin-001",
) -> ExtractedTextBlock:
    return ExtractedTextBlock(
        block_id=block_id,
        source_type=SourceType.LINKEDIN,
        source_ref=source_ref,
        text=json.dumps(payload, sort_keys=True),
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=("linkedin-provenance-001",),
    )


def test_normalizes_structured_experience_and_preserves_traceability() -> None:
    block = _block(
        {
            "experience": [
                {
                    "position": "Senior Director – Service Design",
                    "companyName": "Example Corp",
                    "startDate": {"month": 4, "year": 2021},
                    "endDate": {"text": "Present"},
                    "description": "Led service design work.",
                    "location": "Redmond",
                    "employmentType": "Full-time",
                    "workplaceType": "Hybrid",
                }
            ]
        }
    )

    records = normalize_linkedin_experience(block=block)

    assert len(records) == 1
    record = records[0]
    assert record.record_id == "linkedin-block-001:experience:0"
    assert record.role == "Senior Director – Service Design"
    assert record.employer == "Example Corp"
    assert record.start_date is not None
    assert (record.start_date.year, record.start_date.month, record.start_date.day) == (
        2021,
        4,
        1,
    )
    assert record.end_date is None
    assert record.current is True
    assert record.date_precision is DatePrecision.MONTH
    assert record.source_text == "Led service design work."
    assert record.skill_refs == ()
    assert record.responsibility_refs == ()
    assert record.evidence_refs == ("linkedin-block-001",)
    assert record.provenance_refs == ("linkedin-provenance-001",)


def test_normalizes_multiple_experience_entries_in_source_order() -> None:
    records = normalize_linkedin_experience(
        block=_block(
            {
                "experience": [
                    {"position": "Engineer", "companyName": "A"},
                    {"position": "Staff Engineer", "companyName": "B"},
                ]
            }
        )
    )

    assert [record.record_id for record in records] == [
        "linkedin-block-001:experience:0",
        "linkedin-block-001:experience:1",
    ]
    assert [record.employer for record in records] == ["A", "B"]


def test_normalizes_apify_dataset_array_envelope() -> None:
    block = ExtractedTextBlock(
        block_id="linkedin-dataset-block",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-001",
        text=json.dumps(
            [
                {"name": "Candidate", "skills": ["Python"]},
                {
                    "experience": [
                        {
                            "position": "Engineer",
                            "companyName": "Example",
                            "startDate": {"year": 2020},
                            "endDate": {"text": "Present"},
                        }
                    ]
                },
            ]
        ),
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=("linkedin-provenance",),
    )

    records = normalize_linkedin_experience(block=block)

    assert len(records) == 1
    assert records[0].record_id == "linkedin-dataset-block:experience:0"
    assert records[0].role == "Engineer"
    assert records[0].employer == "Example"


def test_dataset_items_without_experience_produce_no_records() -> None:
    block = ExtractedTextBlock(
        block_id="linkedin-dataset-block",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-001",
        text=json.dumps([{"name": "Jane Doe", "skills": ["Python"]}]),
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=("linkedin-provenance",),
    )

    assert normalize_linkedin_experience(block=block) == ()


def test_explicit_end_date_is_not_current() -> None:
    record = normalize_linkedin_experience(
        block=_block(
            {
                "experience": [
                    {
                        "startDate": {"month": 2, "year": 2021},
                        "endDate": {"month": 9, "year": 2024},
                    }
                ]
            }
        )
    )[0]

    assert record.current is False
    assert record.end_date is not None
    assert (record.end_date.year, record.end_date.month, record.end_date.day) == (
        2024,
        9,
        1,
    )


def test_missing_description_preserves_raw_observation_as_json() -> None:
    record = normalize_linkedin_experience(
        block=_block(
            {
                "experience": [
                    {
                        "position": "Engineer",
                        "companyName": "Example",
                        "location": "Hyderabad",
                    }
                ]
            }
        )
    )[0]

    source = json.loads(record.source_text)
    assert source["position"] == "Engineer"
    assert source["companyName"] == "Example"
    assert source["location"] == "Hyderabad"


def test_missing_dates_remain_unknown() -> None:
    record = normalize_linkedin_experience(
        block=_block({"experience": [{"position": "Engineer"}]})
    )[0]

    assert record.start_date is None
    assert record.end_date is None
    assert record.current is False
    assert record.date_precision is DatePrecision.UNKNOWN


def test_year_only_dates_are_supported() -> None:
    record = normalize_linkedin_experience(
        block=_block(
            {
                "experience": [
                    {
                        "startDate": {"year": 2020},
                        "endDate": {"year": 2022},
                    }
                ]
            }
        )
    )[0]

    assert record.start_date is not None
    assert (record.start_date.year, record.start_date.month) == (2020, 1)
    assert record.end_date is not None
    assert (record.end_date.year, record.end_date.month) == (2022, 1)
    assert record.date_precision is DatePrecision.YEAR


def test_empty_experience_list_is_valid() -> None:
    assert normalize_linkedin_experience(block=_block({"experience": []})) == ()


def test_missing_experience_field_fails() -> None:
    with pytest.raises(LinkedInNormalizationError, match="missing required 'experience'"):
        normalize_linkedin_experience(block=_block({"profile": {"name": "Candidate"}}))


def test_malformed_json_fails() -> None:
    block = ExtractedTextBlock(
        block_id="linkedin-block",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-1",
        text="{invalid-json",
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=("linkedin-provenance",),
    )

    with pytest.raises(LinkedInNormalizationError, match="not valid JSON"):
        normalize_linkedin_experience(block=block)


def test_non_object_payload_and_non_list_experience_fail() -> None:
    with pytest.raises(LinkedInNormalizationError, match="JSON object or dataset list"):
        normalize_linkedin_experience(
            block=ExtractedTextBlock(
                block_id="linkedin-block",
                source_type=SourceType.LINKEDIN,
                source_ref="linkedin-1",
                text="1",
                extraction_kind=ExtractionKind.PLAIN_TEXT,
                provenance_refs=("linkedin-provenance",),
            )
        )

    with pytest.raises(LinkedInNormalizationError, match="must be a list"):
        normalize_linkedin_experience(block=_block({"experience": {}}))


def test_non_object_experience_entry_fails() -> None:
    with pytest.raises(LinkedInNormalizationError, match=r"experience\[0\] must be an object"):
        normalize_linkedin_experience(block=_block({"experience": ["not-an-object"]}))


@pytest.mark.parametrize(
    "start_date",
    [
        {"month": 13, "year": 2024},
        {"month": 5},
        {"month": True, "year": 2024},
        {"year": 0},
    ],
)
def test_invalid_start_date_fails(start_date: dict) -> None:
    with pytest.raises(LinkedInNormalizationError):
        normalize_linkedin_experience(
            block=_block({"experience": [{"startDate": start_date}]})
        )


def test_present_and_explicit_end_date_fails() -> None:
    with pytest.raises(LinkedInNormalizationError, match="both Present and an explicit date"):
        normalize_linkedin_experience(
            block=_block(
                {
                    "experience": [
                        {
                            "endDate": {
                                "month": 3,
                                "year": 2025,
                                "text": "Present",
                            }
                        }
                    ]
                }
            )
        )


def test_wrong_source_type_fails() -> None:
    block = ExtractedTextBlock(
        block_id="resume-block",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        text=json.dumps({"experience": []}),
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=("resume-provenance",),
    )

    with pytest.raises(LinkedInNormalizationError, match="requires a LinkedIn"):
        normalize_linkedin_experience(block=block)


def test_normalization_is_deterministic() -> None:
    block = _block(
        {
            "experience": [
                {
                    "position": "Engineer",
                    "startDate": {"month": 1, "year": 2022},
                    "endDate": {"text": "Present"},
                    "description": "Engineering work.",
                }
            ]
        }
    )

    first = normalize_linkedin_experience(block=block)
    second = normalize_linkedin_experience(block=block)
    assert first == second


def test_normalization_exports_package_entry_point() -> None:
    from vikat_hire.normalization import normalize_linkedin_experience as exported

    assert exported is normalize_linkedin_experience
