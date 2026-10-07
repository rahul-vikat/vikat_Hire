"""Shared artifact checks for the JD and resume extraction adapters."""

from vikat_hire.contracts.common import InputKind, SourceType
from vikat_hire.contracts.inputs import DocumentInput
from vikat_hire.contracts.normalization import ExtractedTextBlock
from vikat_hire.orchestration.state import (
    OrchestrationState,
    from_orchestration_state,
    to_orchestration_state,
)


class ExtractionNodeError(ValueError):
    """Extraction adapter input or returned artifact is invalid."""


def extraction_document(
    transport: OrchestrationState,
    *,
    kind: InputKind,
    content: bytes,
    provenance_refs: tuple[str, ...],
) -> DocumentInput:
    state, blocks = from_orchestration_state(transport)
    document = state.screening_input.jd if kind is InputKind.JD else state.screening_input.resume
    if document.kind is not kind:
        raise ExtractionNodeError("document kind does not match extraction node")
    if not isinstance(content, bytes):
        raise ExtractionNodeError("content must be bytes")
    if not provenance_refs or any(
        not isinstance(ref, str) or not ref.strip() for ref in provenance_refs
    ):
        raise ExtractionNodeError("provenance_refs must contain non-blank strings")
    if any(block.source_ref == document.input_id for block in blocks):
        raise ExtractionNodeError("extracted blocks already exist for document")
    return document


def attach_extraction(
    transport: OrchestrationState,
    *,
    document: DocumentInput,
    result: tuple[ExtractedTextBlock, ...],
    provenance_refs: tuple[str, ...],
) -> OrchestrationState:
    state, existing = from_orchestration_state(transport)
    if not isinstance(result, tuple) or not result:
        raise ExtractionNodeError("extractor must return a non-empty tuple of ExtractedTextBlock")
    expected_source = (
        SourceType.JD_FILE if document.kind is InputKind.JD else SourceType.RESUME_FILE
    )
    seen = {block.block_id for block in existing}
    if len(seen) != len(existing):
        raise ExtractionNodeError("duplicate existing block IDs")
    for block in result:
        if not isinstance(block, ExtractedTextBlock):
            raise ExtractionNodeError("extractor must return ExtractedTextBlock objects")
        if block.source_ref != document.input_id or block.source_type is not expected_source:
            raise ExtractionNodeError("extracted block does not match source document")
        if block.provenance_refs != provenance_refs:
            raise ExtractionNodeError("extractor did not preserve provenance references")
        if block.block_id in seen:
            raise ExtractionNodeError("duplicate extracted block ID")
        seen.add(block.block_id)
    return to_orchestration_state(state, extracted_blocks=(*existing, *result))
