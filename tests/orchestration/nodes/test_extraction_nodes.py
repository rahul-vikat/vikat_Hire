from copy import deepcopy
from importlib import import_module
from io import BytesIO

import pytest
from pypdf import PdfWriter

from vikat_hire.contracts.normalization import ExtractionKind
from vikat_hire.orchestration.interrupts import validate_input_state
from vikat_hire.orchestration.nodes.extract_jd import extract_jd_node
from vikat_hire.orchestration.nodes.extract_resume import extract_resume_node
from vikat_hire.orchestration.state import from_orchestration_state, to_orchestration_state


@pytest.fixture(
    params=[
        ("jd", extract_jd_node, "extract_document_text"),
        ("resume", extract_resume_node, "extract_resume_text"),
    ]
)
def adapter(request):
    return request.param


def test_extraction_preserves_state_and_other_blocks(screening_state, extracted_blocks, adapter):
    name, node, _ = adapter
    other = tuple(block for block in extracted_blocks if block.source_ref != f"{name}-1")
    transport = to_orchestration_state(screening_state, extracted_blocks=other)
    before = deepcopy(transport)
    result = node(transport, content=b"Python developer", provenance_refs=("prov-new",))
    state, blocks, _ = from_orchestration_state(result)
    assert state == screening_state
    assert blocks[:-1] == other
    assert blocks[-1].source_ref == f"{name}-1"
    assert blocks[-1].text == "Python developer"
    assert blocks[-1].provenance_refs == ("prov-new",)
    assert transport == before


def test_extraction_then_existing_validation(screening_state):
    transport = to_orchestration_state(screening_state, extracted_blocks=())
    transport = extract_jd_node(transport, content=b"Required Python", provenance_refs=("jd-prov",))
    transport = extract_resume_node(transport, content=b"Python", provenance_refs=("resume-prov",))
    validated = validate_input_state(transport)
    assert from_orchestration_state(validated)[0].required_inputs_missing == ()


@pytest.mark.parametrize(
    "content,refs", [("not bytes", ("prov",)), (b"text", ()), (b"text", (" ",)), (b"", ("prov",))]
)
def test_invalid_extraction_input_fails(screening_state, adapter, content, refs):
    _, node, _ = adapter
    with pytest.raises(ValueError):
        node(
            to_orchestration_state(screening_state, extracted_blocks=()),
            content=content,
            provenance_refs=refs,
        )


def test_existing_extraction_is_not_overwritten(screening_state, extracted_blocks, adapter):
    _, node, _ = adapter
    transport = to_orchestration_state(screening_state, extracted_blocks=extracted_blocks)
    with pytest.raises(ValueError, match="already exist"):
        node(transport, content=b"replacement", provenance_refs=("prov",))


@pytest.mark.parametrize("invalid", ["type", "empty", "identity", "provenance", "duplicate"])
def test_invalid_service_output_rejected(
    screening_state, extracted_blocks, adapter, monkeypatch, invalid
):
    name, node, service = adapter
    block = next(block for block in extracted_blocks if block.source_ref == f"{name}-1")
    result = {
        "type": ("bad",),
        "empty": (),
        "identity": (block.model_copy(update={"source_ref": "other"}),),
        "provenance": (block.model_copy(update={"provenance_refs": ("other",)}),),
        "duplicate": (block, block),
    }[invalid]
    monkeypatch.setattr(import_module(node.__module__), service, lambda **kwargs: result)
    with pytest.raises(ValueError):
        node(
            to_orchestration_state(screening_state, extracted_blocks=()),
            content=b"text",
            provenance_refs=block.provenance_refs,
        )


def test_service_errors_propagate_unchanged(screening_state, adapter, monkeypatch):
    _, node, service = adapter
    error = RuntimeError("storage-independent extraction failure")

    def fail(**kwargs):
        raise error

    monkeypatch.setattr(import_module(node.__module__), service, fail)
    with pytest.raises(RuntimeError) as raised:
        node(
            to_orchestration_state(screening_state, extracted_blocks=()),
            content=b"text",
            provenance_refs=("prov",),
        )
    assert raised.value is error


def test_resume_adapter_uses_existing_ocr_fallback(screening_state):
    document = screening_state.screening_input.resume.model_copy(
        update={
            "filename": "resume.pdf",
            "media_type": "application/pdf",
        }
    )
    state = screening_state.model_copy(
        update={
            "screening_input": screening_state.screening_input.model_copy(
                update={"resume": document}
            )
        }
    )
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    content = BytesIO()
    writer.write(content)
    calls = []

    def ocr(image):
        calls.append(image)
        return "Python developer"

    result = extract_resume_node(
        to_orchestration_state(state, extracted_blocks=()),
        content=content.getvalue(),
        provenance_refs=("ocr-prov",),
        ocr_text_extractor=ocr,
    )
    restored, blocks, _ = from_orchestration_state(result)
    assert len(calls) == 1
    assert restored == state
    assert blocks[0].extraction_kind is ExtractionKind.OCR_TEXT
    assert blocks[0].provenance_refs == ("ocr-prov",)
