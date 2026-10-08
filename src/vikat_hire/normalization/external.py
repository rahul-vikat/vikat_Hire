from __future__ import annotations

from collections.abc import Iterable, Mapping

from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    NormalizationResult,
    NormalizedSourceState,
)
from vikat_hire.normalization.candidate import normalize_candidate
from vikat_hire.normalization.linkedin import normalize_linkedin_observations

_EXTERNAL_SOURCE_TYPES = frozenset(
    {
        SourceType.LINKEDIN,
        SourceType.GITHUB,
        SourceType.PORTFOLIO,
    }
)


def normalize_external_sources(
    *,
    blocks: Iterable[ExtractedTextBlock],
    screening_id: str,
    source_states: Mapping[str, NormalizedSourceState] | None = None,
) -> NormalizationResult:
    """
    Convert collected external-source text into factual observations.

    This function performs only conservative deterministic normalization.
    It does not perform:
    - JD matching
    - requirement satisfaction
    - semantic evaluation
    - seniority classification
    - suitability evaluation
    - scoring

    LLMs are not used here.
    """

    if not screening_id.strip():
        raise ValueError("screening_id must not be blank")

    block_tuple = tuple(blocks)

    _validate_external_blocks(block_tuple)

    normalized_states = dict(source_states or {})

    _validate_source_states(
        blocks=block_tuple,
        source_states=normalized_states,
    )

    (
        claims,
        skills,
        responsibilities,
        experience_records,
        scope_evidence,
    ) = normalize_candidate(
        blocks=block_tuple,
        screening_id=screening_id,
    )

    linkedin_observations = tuple(
        normalize_linkedin_observations(block=block)
        for block in block_tuple
        if block.source_type is SourceType.LINKEDIN
        and block.text.lstrip().startswith(("{", "["))
    )
    existing_experience_ids = {
        record.record_id for record in experience_records
    }
    experience_records = (
        *experience_records,
        *(
            record
            for record in (
                experience
                for normalized in linkedin_observations
                for experience in normalized[0]
            )
            if record.record_id not in existing_experience_ids
        ),
    )
    existing_skill_ids = {item.skill_id for item in skills}
    skills = (
        *skills,
        *(
            item
            for normalized in linkedin_observations
            for item in normalized[1]
            if item.skill_id not in existing_skill_ids
        ),
    )
    existing_responsibility_ids = {
        item.responsibility_id for item in responsibilities
    }
    responsibilities = (
        *responsibilities,
        *(
            item
            for normalized in linkedin_observations
            for item in normalized[2]
            if item.responsibility_id not in existing_responsibility_ids
        ),
    )

    provenance_refs = _dedupe(
        provenance_ref
        for block in block_tuple
        for provenance_ref in block.provenance_refs
    )

    return NormalizationResult(
        screening_id=screening_id,
        extracted_blocks=block_tuple,
        claims=claims,
        skills=skills,
        responsibilities=responsibilities,
        experience_records=experience_records,
        scope_evidence=scope_evidence,
        source_states=normalized_states,
        provenance_refs=provenance_refs,
    )


def _validate_external_blocks(
    blocks: tuple[ExtractedTextBlock, ...],
) -> None:
    seen_ids: set[str] = set()

    for block in blocks:
        if block.block_id in seen_ids:
            raise ValueError(
                f"duplicate extracted block id: {block.block_id}"
            )

        seen_ids.add(block.block_id)

        if block.source_type not in _EXTERNAL_SOURCE_TYPES:
            raise ValueError(
                "external normalization only accepts LinkedIn, GitHub, "
                "or Portfolio blocks; received "
                f"{block.source_type.value!r}"
            )


def _validate_source_states(
    *,
    blocks: tuple[ExtractedTextBlock, ...],
    source_states: Mapping[str, NormalizedSourceState],
) -> None:
    block_source_refs = {
        block.source_ref
        for block in blocks
    }

    for source_ref, state in source_states.items():
        if not source_ref.strip():
            raise ValueError(
                "source state reference must not be blank"
            )

        if state is NormalizedSourceState.AVAILABLE:
            if source_ref not in block_source_refs:
                raise ValueError(
                    "available external source must have extracted blocks: "
                    f"{source_ref}"
                )
            continue

        if source_ref in block_source_refs:
            raise ValueError(
                "non-available external source cannot have extracted blocks: "
                f"{source_ref}"
            )


def _dedupe(
    values: Iterable[str],
) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return tuple(result)
