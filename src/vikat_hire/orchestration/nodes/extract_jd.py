from vikat_hire.contracts.common import InputKind
from vikat_hire.normalization.document import extract_document_text
from vikat_hire.orchestration.nodes._extraction import attach_extraction, extraction_document
from vikat_hire.orchestration.state import OrchestrationState


def extract_jd_node(
    transport: OrchestrationState,
    *,
    content: bytes,
    provenance_refs: tuple[str, ...],
) -> OrchestrationState:
    """Delegate document parsing and attach JD blocks without changing domain state.

    Bytes are supplied by the caller; this node does not choose a storage backend.
    Extraction errors propagate unchanged. Missing-input handling stays in validation.
    """
    document = extraction_document(
        transport, kind=InputKind.JD, content=content, provenance_refs=provenance_refs
    )
    result = extract_document_text(
        document=document, content=content, provenance_refs=provenance_refs
    )
    return attach_extraction(
        transport, document=document, result=result, provenance_refs=provenance_refs
    )
