from io import BytesIO

import pytest
from pypdf import PdfWriter

from vikat_hire.collection.resume_extractor import extract_resume_text
from vikat_hire.contracts.common import InputKind
from vikat_hire.contracts.inputs import DocumentInput
from vikat_hire.contracts.normalization import ExtractionKind


def _resume_document() -> DocumentInput:
    return DocumentInput(
        input_id="resume-001",
        kind=InputKind.RESUME,
        filename="resume.pdf",
        media_type="application/pdf",
        content_hash="hash",
        storage_ref="storage://resume",
    )


def _pdf_with_blank_page() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def test_normal_extraction_success_does_not_call_ocr(monkeypatch):
    called = False

    def fake_ocr(_image):
        nonlocal called
        called = True
        return "OCR text"

    result = extract_resume_text(
        document=DocumentInput(
            input_id="resume-001",
            kind=InputKind.RESUME,
            filename="resume.txt",
            media_type="text/plain",
            content_hash="hash",
            storage_ref="storage://resume",
        ),
        content=b"Python Developer",
        provenance_refs=("prov-resume",),
        ocr_text_extractor=fake_ocr,
    )

    assert called is False
    assert result[0].text == "Python Developer"
    assert result[0].extraction_kind is ExtractionKind.PLAIN_TEXT


def test_failed_pdf_extraction_calls_ocr():
    calls = 0

    def fake_ocr(_image):
        nonlocal calls
        calls += 1
        return "Python Developer\nOwned APIs."

    result = extract_resume_text(
        document=_resume_document(),
        content=_pdf_with_blank_page(),
        provenance_refs=("prov-resume",),
        ocr_text_extractor=fake_ocr,
    )

    assert calls == 1
    assert result[0].text == "Python Developer\nOwned APIs."
    assert result[0].extraction_kind is ExtractionKind.OCR_TEXT
    assert result[0].page_number == 1
    assert result[0].provenance_refs == ("prov-resume",)


def test_ocr_output_uses_same_extracted_text_block_contract():
    result = extract_resume_text(
        document=_resume_document(),
        content=_pdf_with_blank_page(),
        provenance_refs=("prov-resume",),
        ocr_text_extractor=lambda _image: "  Python  \n\n Developer  ",
    )

    block = result[0]

    assert block.source_type.value == "resume_file"
    assert block.source_ref == "resume-001"
    assert block.text == "Python\n\nDeveloper"
    assert block.extraction_kind is ExtractionKind.OCR_TEXT


def test_ocr_empty_output_fails_loudly():
    with pytest.raises(
        ValueError,
        match="normal resume text extraction failed and OCR fallback failed",
    ):
        extract_resume_text(
            document=_resume_document(),
            content=_pdf_with_blank_page(),
            provenance_refs=("prov-resume",),
            ocr_text_extractor=lambda _image: " \n\t ",
        )


def test_ocr_failure_fails_loudly():
    def failing_ocr(_image):
        raise RuntimeError("tesseract unavailable")

    with pytest.raises(
        ValueError,
        match="normal resume text extraction failed and OCR fallback failed",
    ):
        extract_resume_text(
            document=_resume_document(),
            content=_pdf_with_blank_page(),
            provenance_refs=("prov-resume",),
            ocr_text_extractor=failing_ocr,
        )


def test_non_pdf_normal_extraction_failure_does_not_call_ocr():
    called = False

    def fake_ocr(_image):
        nonlocal called
        called = True
        return "should not run"

    document = DocumentInput(
        input_id="resume-001",
        kind=InputKind.RESUME,
        filename="resume.docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        content_hash="hash",
        storage_ref="storage://resume",
    )

    with pytest.raises(ValueError, match="failed to parse DOCX"):
        extract_resume_text(
            document=document,
            content=b"not a docx",
            provenance_refs=("prov-resume",),
            ocr_text_extractor=fake_ocr,
        )

    assert called is False