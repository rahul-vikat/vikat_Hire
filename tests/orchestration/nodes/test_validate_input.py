from datetime import UTC, datetime

import pytest

from vikat_hire.contracts.common import InputKind, SourceType, WorkflowStatus
from vikat_hire.contracts.inputs import DocumentInput, ScreeningInput
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    ExtractionKind,
    NormalizationResult,
)
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.normalization.document import extract_document_text
from vikat_hire.orchestration.nodes.validate_input import (
    InputValidationNodeError,
    validate_input_node,
)
from vikat_hire.orchestration.routing import route_after_input_validation


def _state() -> ScreeningState:
    return ScreeningState(
        screening_id="screening-1",
        screening_input=ScreeningInput(
            screening_id="screening-1",
            jd=_document(InputKind.JD),
            resume=_document(InputKind.RESUME),
        ),
        current_node="validate_input",
        revision=7,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        errors=("existing error",),
    )


def _document(kind: InputKind) -> DocumentInput:
    return DocumentInput(
        input_id=f"{kind.value}-1",
        kind=kind,
        filename=f"{kind.value}.txt",
        media_type="text/plain",
        content_hash="opaque-hash",
        storage_ref=f"documents/{kind.value}",
    )


def _blocks(state: ScreeningState) -> tuple[ExtractedTextBlock, ...]:
    return tuple(
        block
        for document in (state.screening_input.jd, state.screening_input.resume)
        for block in extract_document_text(
            document=document,
            content=b"Python development and production ownership.",
            provenance_refs=(f"provenance-{document.input_id}",),
        )
    )


def test_existing_extraction_output_allows_classification_and_preserves_state() -> None:
    state = _state()
    blocks = _blocks(state)
    normalization = NormalizationResult(screening_id=state.screening_id, extracted_blocks=blocks)
    result = validate_input_node(state, extracted_blocks=normalization.extracted_blocks)

    assert result == state
    assert result is not state
    assert result.screening_input is state.screening_input
    assert route_after_input_validation(result) == "classify_jd"
    assert normalization.extracted_blocks == blocks


@pytest.mark.parametrize("name", ["jd", "resume"])
@pytest.mark.parametrize("field", ["filename", "media_type", "content_hash", "storage_ref"])
@pytest.mark.parametrize("value", ["", " \t\n"])
def test_blank_metadata_interrupts_even_with_usable_content(name, field, value) -> None:
    state = _state()
    document = getattr(state.screening_input, name).model_copy(update={field: value})
    state = state.model_copy(
        update={"screening_input": state.screening_input.model_copy(update={name: document})}
    )
    result = validate_input_node(state, extracted_blocks=_blocks(_state()))

    assert result.required_inputs_missing == (f"{name}.{field}",)
    assert result.status is WorkflowStatus.WAITING_FOR_INPUT
    assert route_after_input_validation(result) == "interrupt"


@pytest.mark.parametrize("missing_name", ["jd", "resume", "both"])
def test_metadata_without_required_content_interrupts(missing_name) -> None:
    state = _state()
    blocks = tuple(
        block
        for block in _blocks(state)
        if missing_name != "both" and block.source_ref != f"{missing_name}-1"
    )
    result = validate_input_node(state, extracted_blocks=blocks)
    names = ("jd", "resume") if missing_name == "both" else (missing_name,)

    assert result.required_inputs_missing == tuple(f"{name}.extracted_content" for name in names)
    assert result.status is WorkflowStatus.WAITING_FOR_INPUT
    assert route_after_input_validation(result) == "interrupt"


@pytest.mark.parametrize("name", ["jd", "resume"])
def test_absent_document_is_reported_without_weakening_contracts(name) -> None:
    state = _state()
    blocks = tuple(block for block in _blocks(state) if block.source_ref != f"{name}-1")
    # model_copy bypasses validation; normal ScreeningInput construction requires
    # both documents. Exercise the node's defensive absent-document handling.
    state = state.model_copy(
        update={"screening_input": state.screening_input.model_copy(update={name: None})}
    )
    result = validate_input_node(state, extracted_blocks=blocks)

    assert result.required_inputs_missing == (name, f"{name}.extracted_content")
    assert result.status is WorkflowStatus.WAITING_FOR_INPUT


def test_missing_fields_have_stable_document_and_field_order() -> None:
    state = _state()
    documents = {
        name: getattr(state.screening_input, name).model_copy(
            update=dict.fromkeys(("filename", "media_type", "content_hash", "storage_ref"), " ")
        )
        for name in ("jd", "resume")
    }
    state = state.model_copy(
        update={"screening_input": state.screening_input.model_copy(update=documents)}
    )
    result = validate_input_node(state, extracted_blocks=())
    assert result.required_inputs_missing == tuple(
        f"{name}.{field}"
        for name in ("jd", "resume")
        for field in ("filename", "media_type", "content_hash", "storage_ref", "extracted_content")
    )


def test_revalidation_clears_resolved_keys_and_releases_input_wait() -> None:
    original = _state()
    waiting = validate_input_node(original, extracted_blocks=())
    assert validate_input_node(waiting, extracted_blocks=()) == waiting
    result = validate_input_node(waiting, extracted_blocks=iter(_blocks(original)))

    assert result.status is WorkflowStatus.EVALUATING
    assert result.required_inputs_missing == ()
    assert route_after_input_validation(result) == "classify_jd"
    unchanged = set(ScreeningState.model_fields) - {"status", "required_inputs_missing"}
    for field in unchanged:
        assert getattr(result, field) == getattr(original, field)
        assert getattr(waiting, field) == getattr(original, field)
    assert original.status is WorkflowStatus.CREATED
    assert original.required_inputs_missing == ()


def test_unrelated_missing_inputs_remain_blocking() -> None:
    state = _state().model_copy(
        update={
            "required_inputs_missing": (
                "jd.filename",
                "resume.extracted_content",
                "other.required",
            ),
            "status": WorkflowStatus.WAITING_FOR_INPUT,
        }
    )
    result = validate_input_node(state, extracted_blocks=_blocks(state))
    assert result.required_inputs_missing == ("other.required",)
    assert result.status is WorkflowStatus.WAITING_FOR_INPUT
    assert route_after_input_validation(result) == "interrupt"


@pytest.mark.parametrize("kind", list(ExtractionKind))
def test_existing_extraction_kinds_are_accepted(kind) -> None:
    state = _state()
    blocks = tuple(block.model_copy(update={"extraction_kind": kind}) for block in _blocks(state))
    assert validate_input_node(state, extracted_blocks=blocks).required_inputs_missing == ()


def test_external_content_cannot_substitute_for_jd_or_resume() -> None:
    state = _state()
    external = _blocks(state)[0].model_copy(update={"source_type": SourceType.LINKEDIN})
    result = validate_input_node(state, extracted_blocks=(external,))
    assert result.required_inputs_missing == ("jd.extracted_content", "resume.extracted_content")


@pytest.mark.parametrize("text", ["", " \n\t"])
def test_unvalidated_blank_text_is_missing_content(text) -> None:
    state = _state()
    jd, resume = _blocks(state)
    jd = jd.model_copy(update={"text": text})
    result = validate_input_node(state, extracted_blocks=(jd, resume))
    assert result.required_inputs_missing == ("jd.extracted_content",)
    assert result.status is WorkflowStatus.WAITING_FOR_INPUT


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"source_ref": "another-document"}, "does not reference"),
        ({"source_type": SourceType.RESUME_FILE}, "does not reference"),
        ({"provenance_refs": ()}, "provenance references"),
        ({"provenance_refs": (" ",)}, "provenance references"),
        ({"text": None}, "text must be a string"),
    ],
)
def test_malformed_artifacts_fail_loudly(changes, message) -> None:
    state = _state()
    jd, resume = _blocks(state)
    with pytest.raises(InputValidationNodeError, match=message):
        validate_input_node(state, extracted_blocks=(jd.model_copy(update=changes), resume))


def test_duplicate_blocks_fail_loudly() -> None:
    state = _state()
    blocks = _blocks(state)
    with pytest.raises(InputValidationNodeError, match="duplicate extracted block"):
        validate_input_node(state, extracted_blocks=(*blocks, blocks[0]))


@pytest.mark.parametrize("value", [None, {}, "text"])
def test_invalid_state_fails_loudly(value) -> None:
    with pytest.raises(InputValidationNodeError, match="state must be a ScreeningState"):
        validate_input_node(value, extracted_blocks=())


def test_invalid_block_type_fails_loudly() -> None:
    with pytest.raises(InputValidationNodeError, match="ExtractedTextBlock objects"):
        validate_input_node(_state(), extracted_blocks=("text",))


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"kind": InputKind.RESUME}, "incorrect document kind"),
        ({"input_id": " "}, "input_id must not be blank"),
    ],
)
def test_invalid_document_identity_fails_loudly(changes, message) -> None:
    state = _state()
    jd = state.screening_input.jd.model_copy(update=changes)
    state = state.model_copy(
        update={"screening_input": state.screening_input.model_copy(update={"jd": jd})}
    )
    with pytest.raises(InputValidationNodeError, match=message):
        validate_input_node(state, extracted_blocks=())


def test_extraction_errors_are_not_swallowed() -> None:
    def failing_blocks():
        raise ValueError("extraction failed")
        yield

    with pytest.raises(ValueError, match="extraction failed"):
        validate_input_node(_state(), extracted_blocks=failing_blocks())
