from __future__ import annotations

from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    NormalizationResult,
)
from vikat_hire.orchestration.state import OrchestrationState, from_orchestration_state
from vikat_hire.normalization.candidate import normalize_candidate
from vikat_hire.normalization.jd import normalize_jd


class NormalizationNodeError(ValueError):
    """Raised when normalization orchestration input is invalid."""


def normalize_node(
    transport: OrchestrationState,
) -> OrchestrationState:
    """
    Normalize JD and resume extraction artifacts into the authoritative
    NormalizationResult.

    This node only creates factual normalization artifacts.

    It does not:
    - classify JD technical/non-technical;
    - match requirements;
    - perform semantic evaluation;
    - evaluate seniority;
    - evaluate external evidence;
    - calculate a score;
    - apply policy;
    - invoke an LLM.
    """

    try:
        state, blocks, _ = from_orchestration_state(transport)
    except Exception as exc:
        if isinstance(exc, NormalizationNodeError):
            raise
        raise NormalizationNodeError(
            f"invalid orchestration state: {exc}"
        ) from exc

    if not blocks:
        raise NormalizationNodeError(
            "cannot normalize without extracted text blocks"
        )

    jd_blocks = tuple(
        block
        for block in blocks
        if block.source_type is SourceType.JD_FILE
    )

    resume_blocks = tuple(
        block
        for block in blocks
        if block.source_type is SourceType.RESUME_FILE
    )

    if not jd_blocks:
        raise NormalizationNodeError(
            "cannot normalize without JD extracted blocks"
        )

    if not resume_blocks:
        raise NormalizationNodeError(
            "cannot normalize without resume extracted blocks"
        )

    try:
        (
            jd_requirements,
            jd_experience_requirements,
            jd_scope_evidence,
        ) = normalize_jd(
            blocks=jd_blocks,
            screening_id=state.screening_id,
        )

        (
            claims,
            skills,
            responsibilities,
            experience_records,
            scope_evidence,
        ) = normalize_candidate(
            blocks=resume_blocks,
            screening_id=state.screening_id,
        )
    except Exception as exc:
        raise NormalizationNodeError(
            f"deterministic normalization failed: {exc}"
        ) from exc

    provenance_refs = _ordered_unique(
        provenance_ref
        for block in blocks
        for provenance_ref in block.provenance_refs
    )

    normalization = NormalizationResult(
        screening_id=state.screening_id,
        extracted_blocks=blocks,
        claims=claims,
        skills=skills,
        responsibilities=responsibilities,
        experience_records=experience_records,
        scope_evidence=scope_evidence,
        jd_requirements=jd_requirements,
        jd_experience_requirements=jd_experience_requirements,
        jd_scope_evidence=jd_scope_evidence,
        provenance_refs=provenance_refs,
    )

    return {
        **transport,
        "normalization": normalization.model_dump(mode="python"),
    }


def _ordered_unique(values: object) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if not isinstance(value, str):
            raise NormalizationNodeError(
                "provenance references must be strings"
            )

        if not value.strip():
            raise NormalizationNodeError(
                "provenance references must not be blank"
            )

        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return tuple(result)