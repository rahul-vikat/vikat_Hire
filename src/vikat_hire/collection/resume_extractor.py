from __future__ import annotations

import hashlib
from collections.abc import Callable
from io import BytesIO

import pypdfium2 as pdfium
import pytesseract

from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.inputs import DocumentInput
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    ExtractionKind,
)
from vikat_hire.normalization.document import extract_document_text


OCRTextExtractor = Callable[[object], str]


def extract_resume_text(
    *,
    document: DocumentInput,
    content: bytes,
    provenance_refs: tuple[str, ...],
    ocr_text_extractor: OCRTextExtractor | None = None,
) -> tuple[ExtractedTextBlock, ...]:
    """Extract resume text, using Tesseract only after normal extraction fails."""
    try:
        return extract_document_text(
            document=document,
            content=content,
            provenance_refs=provenance_refs,
        )
    except ValueError:
        if not _is_pdf(document):
            raise

        try:
            return _extract_pdf_with_ocr(
                document=document,
                content=content,
                provenance_refs=provenance_refs,
                ocr_text_extractor=ocr_text_extractor,
            )
        except Exception as exc:
            raise ValueError(
                "normal resume text extraction failed and OCR fallback failed"
            ) from exc


def _is_pdf(document: DocumentInput) -> bool:
    media_type = document.media_type.strip().lower()
    filename = document.filename.strip().lower()
    return media_type == "application/pdf" or filename.endswith(".pdf")


def _extract_pdf_with_ocr(
    *,
    document: DocumentInput,
    content: bytes,
    provenance_refs: tuple[str, ...],
    ocr_text_extractor: OCRTextExtractor | None,
) -> tuple[ExtractedTextBlock, ...]:
    if not content:
        raise ValueError("resume content must not be empty")

    if not provenance_refs:
        raise ValueError("provenance_refs must contain at least one reference")

    try:
        pdf = pdfium.PdfDocument(BytesIO(content))
    except Exception as exc:
        raise ValueError("failed to open PDF for OCR") from exc

    blocks: list[ExtractedTextBlock] = []

    try:
        for page_number in range(1, len(pdf) + 1):
            page = pdf[page_number - 1]

            try:
                bitmap = page.render(scale=2.0)

                try:
                    image = bitmap.to_pil()

                    if ocr_text_extractor is None:
                        text = pytesseract.image_to_string(image)
                    else:
                        text = ocr_text_extractor(image)
                finally:
                    bitmap.close()

                normalized = _normalize_text(text)

                if not normalized:
                    continue

                blocks.append(
                    ExtractedTextBlock(
                        block_id=_ocr_block_id(
                            source_ref=document.input_id,
                            page_number=page_number,
                            text=normalized,
                        ),
                        source_type=SourceType.RESUME_FILE,
                        source_ref=document.input_id,
                        text=normalized,
                        page_number=page_number,
                        section=None,
                        extraction_kind=ExtractionKind.OCR_TEXT,
                        provenance_refs=provenance_refs,
                    )
                )
            finally:
                page.close()
    finally:
        pdf.close()

    if not blocks:
        raise ValueError("OCR produced no extractable text")

    return tuple(blocks)


def _normalize_text(text: str) -> str:
    lines = [
        line.strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]

    while lines and not lines[0]:
        lines.pop()

    while lines and not lines[-1]:
        lines.pop()

    return "\n".join(lines)


def _ocr_block_id(
    *,
    source_ref: str,
    page_number: int,
    text: str,
) -> str:
    payload = "\x1f".join(
        (
            source_ref,
            str(page_number),
            "ocr",
            text,
        )
    ).encode()

    return "block-" + hashlib.sha256(payload).hexdigest()