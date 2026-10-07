from vikat_hire.collection.resume_extractor import OCRTextExtractor, extract_resume_text
from vikat_hire.contracts.common import InputKind
from vikat_hire.orchestration.nodes._extraction import attach_extraction, extraction_document
from vikat_hire.orchestration.state import OrchestrationState


def extract_resume_node(
    transport: OrchestrationState,
    *,
    content: bytes,
    provenance_refs: tuple[str, ...],
    ocr_text_extractor: OCRTextExtractor | None = None,
) -> OrchestrationState:
    """Delegate to the existing resume/OCR service and preserve all prior artifacts."""
    document = extraction_document(
        transport, kind=InputKind.RESUME, content=content, provenance_refs=provenance_refs
    )
    result = extract_resume_text(
        document=document,
        content=content,
        provenance_refs=provenance_refs,
        ocr_text_extractor=ocr_text_extractor,
    )
    return attach_extraction(
        transport, document=document, result=result, provenance_refs=provenance_refs
    )
