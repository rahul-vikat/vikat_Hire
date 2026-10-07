from __future__ import annotations

import hashlib
from io import BytesIO

from docx import Document as DocxDocument
from pypdf import PdfReader

from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.inputs import DocumentInput
from vikat_hire.contracts.normalization import ExtractedTextBlock, ExtractionKind

_PDF_TYPES = {"application/pdf"}
_DOCX_TYPES = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
_TEXT_TYPES = {"text/plain", "text/markdown", "text/x-markdown"}


def extract_document_text(*, document: DocumentInput, content: bytes, provenance_refs: tuple[str, ...]) -> tuple[ExtractedTextBlock, ...]:
    if not content:
        raise ValueError("document content must not be empty")
    if not provenance_refs:
        raise ValueError("provenance_refs must contain at least one reference")
    media_type = document.media_type.strip().lower()
    filename = document.filename.strip().lower()
    if media_type in _PDF_TYPES or filename.endswith(".pdf"):
        return _extract_pdf(document=document, content=content, provenance_refs=provenance_refs)
    if media_type in _DOCX_TYPES or filename.endswith(".docx"):
        return _extract_docx(document=document, content=content, provenance_refs=provenance_refs)
    if media_type in _TEXT_TYPES or filename.endswith((".txt", ".text", ".md", ".markdown")):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("plain-text document must be valid UTF-8") from exc
        return (_build_block(document=document, ordinal=0, text=text, page_number=None, section=None, extraction_kind=ExtractionKind.PLAIN_TEXT, provenance_refs=provenance_refs),)
    raise ValueError(f"unsupported document format: media_type={document.media_type!r}, filename={document.filename!r}")


def _normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _block_id(*, source_ref: str, ordinal: int, text: str, page_number: int | None, section: str | None) -> str:
    payload = "\x1f".join((source_ref, str(ordinal), str(page_number or ""), section or "", text)).encode()
    return "block-" + hashlib.sha256(payload).hexdigest()


def _source_type(document: DocumentInput) -> SourceType:
    if document.kind.value == "jd":
        return SourceType.JD_FILE
    if document.kind.value == "resume":
        return SourceType.RESUME_FILE
    raise ValueError(f"unsupported document input kind for normalization: {document.kind!r}")


def _build_block(*, document: DocumentInput, ordinal: int, text: str, page_number: int | None, section: str | None, extraction_kind: ExtractionKind, provenance_refs: tuple[str, ...]) -> ExtractedTextBlock:
    normalized = _normalize_text(text)
    if not normalized:
        raise ValueError(f"document contains an empty extracted text block: ordinal={ordinal}")
    return ExtractedTextBlock(block_id=_block_id(source_ref=document.input_id, ordinal=ordinal, text=normalized, page_number=page_number, section=section), source_type=_source_type(document), source_ref=document.input_id, text=normalized, page_number=page_number, section=section, extraction_kind=extraction_kind, provenance_refs=provenance_refs)


def _extract_pdf(*, document: DocumentInput, content: bytes, provenance_refs: tuple[str, ...]) -> tuple[ExtractedTextBlock, ...]:
    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise ValueError("failed to parse PDF document") from exc
    blocks = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise ValueError(f"failed to extract text from PDF page {page_number}") from exc
        if _normalize_text(text):
            blocks.append(_build_block(document=document, ordinal=page_number - 1, text=text, page_number=page_number, section=None, extraction_kind=ExtractionKind.PDF_TEXT, provenance_refs=provenance_refs))
    if not blocks:
        raise ValueError("PDF document produced no extractable text")
    return tuple(blocks)


def _extract_docx(*, document: DocumentInput, content: bytes, provenance_refs: tuple[str, ...]) -> tuple[ExtractedTextBlock, ...]:
    try:
        source = DocxDocument(BytesIO(content))
    except Exception as exc:
        raise ValueError("failed to parse DOCX document") from exc
    blocks = []
    section = None
    for ordinal, paragraph in enumerate(source.paragraphs):
        text = _normalize_text(paragraph.text)
        if not text:
            continue
        style = paragraph.style.name.strip() if paragraph.style is not None and paragraph.style.name else ""
        if style.lower().startswith("heading"):
            section = text
        blocks.append(_build_block(document=document, ordinal=ordinal, text=text, page_number=None, section=section, extraction_kind=ExtractionKind.DOCX_TEXT, provenance_refs=provenance_refs))
    if not blocks:
        raise ValueError("DOCX document produced no extractable text")
    return tuple(blocks)
