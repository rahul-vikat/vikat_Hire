from __future__ import annotations

from collections.abc import Iterable

from vikat_hire.contracts.common import InputKind, SourceType, WorkflowStatus
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.normalization import ExtractedTextBlock
from vikat_hire.contracts.state import ScreeningState

_METADATA_FIELDS = ("filename", "media_type", "content_hash", "storage_ref")
_OWNED_MISSING_FIELDS = frozenset(
    key
    for name in ("jd", "resume")
    for key in (
        name,
        *(f"{name}.{field}" for field in _METADATA_FIELDS),
        f"{name}.extracted_content",
    )
)


class InputValidationNodeError(ValueError):
    """Raised for invalid validation artifacts rather than missing user input."""


def validate_input_node(
    state: ScreeningState,
    *,
    extracted_blocks: Iterable[ExtractedTextBlock],
) -> ScreeningState:
    """Validate metadata and existing extraction output without extracting again.

    Pass extraction output (or NormalizationResult.extracted_blocks) explicitly;
    ScreeningState does not currently store these artifacts. Empty output is
    missing content, never proof that document metadata is sufficient.

    Missing keys are jd/resume for an absent document, <document>.<field> for
    blank metadata, and <document>.extracted_content for absent usable text.
    JD keys precede resume keys. Unrelated missing-input keys are preserved.
    Metadata is checked for non-blank strings: storage references are opaque,
    and this node does not impose new hash, MIME, or storage-provider formats.

    Only required_inputs_missing and status can change. A satisfied input wait
    advances to EVALUATING for classification/matching; other statuses remain
    unchanged. Revision, timestamps, provenance, and results are preserved.
    """
    if not isinstance(state, ScreeningState):
        raise InputValidationNodeError("state must be a ScreeningState")
    if not isinstance(state.screening_input, ScreeningInput):
        raise InputValidationNodeError("screening_input must be a ScreeningInput")

    documents: dict[SourceType, DocumentInput | None] = {}
    missing: list[str] = []
    for name, kind, source_type in (
        ("jd", InputKind.JD, SourceType.JD_FILE),
        ("resume", InputKind.RESUME, SourceType.RESUME_FILE),
    ):
        # Normal construction requires both documents. Handle absent documents
        # defensively without weakening those contracts for partial input.
        document = getattr(state.screening_input, name, None)
        if document is not None:
            if not isinstance(document, DocumentInput):
                raise InputValidationNodeError(f"{name} must be a DocumentInput")
            if document.kind is not kind:
                raise InputValidationNodeError(f"{name} has incorrect document kind")
            if not isinstance(document.input_id, str) or not document.input_id.strip():
                raise InputValidationNodeError(f"{name}.input_id must not be blank")
        documents[source_type] = document

    usable_sources: set[SourceType] = set()
    seen: set[str] = set()
    for block in extracted_blocks:
        if not isinstance(block, ExtractedTextBlock):
            raise InputValidationNodeError(
                "extracted_blocks must contain ExtractedTextBlock objects"
            )
        if block.block_id in seen:
            raise InputValidationNodeError(f"duplicate extracted block ID: {block.block_id}")
        seen.add(block.block_id)
        if block.source_type not in documents:
            continue
        document = documents[block.source_type]
        if document is None or block.source_ref != document.input_id:
            raise InputValidationNodeError("extracted block does not reference its input document")
        if not block.provenance_refs or any(
            not isinstance(ref, str) or not ref.strip() for ref in block.provenance_refs
        ):
            raise InputValidationNodeError(
                "extracted block must have non-blank provenance references"
            )
        if not isinstance(block.text, str):
            raise InputValidationNodeError("extracted block text must be a string")
        if block.text.strip():
            usable_sources.add(block.source_type)

    for name, source_type in (("jd", SourceType.JD_FILE), ("resume", SourceType.RESUME_FILE)):
        document = documents[source_type]
        if document is None:
            missing.append(name)
        else:
            for field in _METADATA_FIELDS:
                value = getattr(document, field, None)
                if not isinstance(value, str) or not value.strip():
                    missing.append(f"{name}.{field}")
        if source_type not in usable_sources:
            missing.append(f"{name}.extracted_content")

    missing.extend(key for key in state.required_inputs_missing if key not in _OWNED_MISSING_FIELDS)
    status = state.status
    if missing:
        status = WorkflowStatus.WAITING_FOR_INPUT
    elif status is WorkflowStatus.WAITING_FOR_INPUT:
        status = WorkflowStatus.EVALUATING

    return state.model_copy(update={"required_inputs_missing": tuple(missing), "status": status})
