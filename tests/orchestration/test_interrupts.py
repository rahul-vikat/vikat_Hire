from copy import deepcopy

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pydantic import ValidationError

from vikat_hire.contracts.common import WorkflowStatus
from vikat_hire.orchestration.interrupts import (
    InputInterruptionError,
    InputResume,
    create_input_checkpoint,
    interrupt_missing_input,
    restore_input_checkpoint,
    resume_missing_input,
    validate_input_state,
)
from vikat_hire.orchestration.state import (
    OrchestrationState,
    from_orchestration_state,
    to_orchestration_state,
)


def _waiting(state):
    return validate_input_state(to_orchestration_state(state, extracted_blocks=()))


def _payload(state, blocks):
    return InputResume(screening_input=state.screening_input, extracted_blocks=blocks).model_dump()


def _graph(checkpointer):
    # Test harness only: the production screening graph remains unimplemented.
    builder = StateGraph(OrchestrationState)
    builder.add_node("validate", validate_input_state)
    builder.add_node("interrupt", interrupt_missing_input)
    builder.add_edge(START, "validate")
    builder.add_conditional_edges(
        "validate",
        lambda transport: (
            "interrupt" if from_orchestration_state(transport)[0].required_inputs_missing else END
        ),
    )
    builder.add_edge("interrupt", END)
    return builder.compile(checkpointer=checkpointer)


def test_checkpoint_roundtrip_preserves_every_field(screening_state, extracted_blocks):
    waiting = _waiting(screening_state)
    checkpoint = create_input_checkpoint(waiting)
    restored = restore_input_checkpoint(
        checkpoint, screening_id=screening_state.screening_id, extracted_blocks=()
    )
    assert restored == waiting
    assert checkpoint.revision == screening_state.revision
    assert checkpoint.current_node == screening_state.current_node
    assert checkpoint.state.status is WorkflowStatus.WAITING_FOR_INPUT
    result = resume_missing_input(restored, _payload(screening_state, extracted_blocks))
    resumed, blocks = from_orchestration_state(result)
    assert blocks == extracted_blocks
    assert resumed == screening_state.model_copy(update={"status": WorkflowStatus.EVALUATING})


def test_partial_resume_remains_waiting_and_preserves_original(screening_state, extracted_blocks):
    waiting = _waiting(screening_state)
    before = deepcopy(waiting)
    partial = resume_missing_input(waiting, _payload(screening_state, extracted_blocks[:1]))
    state, blocks = from_orchestration_state(partial)
    assert state.required_inputs_missing == ("resume.extracted_content",)
    assert state.status is WorkflowStatus.WAITING_FOR_INPUT
    assert blocks == extracted_blocks[:1]
    assert waiting == before


@pytest.mark.parametrize(
    "field,value", [("screening_id", "other"), ("revision", 999), ("current_node", "other")]
)
def test_checkpoint_metadata_mismatch_rejected(screening_state, field, value):
    checkpoint = create_input_checkpoint(_waiting(screening_state)).model_copy(
        update={field: value}
    )
    with pytest.raises(ValueError, match="match"):
        restore_input_checkpoint(
            checkpoint, screening_id=screening_state.screening_id, extracted_blocks=()
        )


def test_wrong_requested_identity_and_invalid_checkpoint_rejected(screening_state):
    checkpoint = create_input_checkpoint(_waiting(screening_state))
    with pytest.raises(InputInterruptionError, match="requested screening"):
        restore_input_checkpoint(checkpoint, screening_id="other", extracted_blocks=())
    with pytest.raises(InputInterruptionError, match="must be a Checkpoint"):
        restore_input_checkpoint(None, screening_id="screening-1", extracted_blocks=())


@pytest.mark.parametrize(
    "status,missing",
    [
        (WorkflowStatus.CREATED, ("jd.extracted_content",)),
        (WorkflowStatus.WAITING_FOR_INPUT, ()),
        (WorkflowStatus.COMPLETED, ("jd.extracted_content",)),
    ],
)
def test_interrupt_resume_and_checkpoint_require_explicit_waiting(screening_state, status, missing):
    state = screening_state.model_copy(
        update={"status": status, "required_inputs_missing": missing}
    )
    transport = to_orchestration_state(state, extracted_blocks=())
    for operation in (interrupt_missing_input, create_input_checkpoint):
        with pytest.raises(InputInterruptionError, match="requires WAITING_FOR_INPUT"):
            operation(transport)
    with pytest.raises(InputInterruptionError):
        resume_missing_input(transport, {})


@pytest.mark.parametrize(
    "payload", [None, "bad", {}, {"screening_input": None, "extracted_blocks": []}]
)
def test_malformed_resume_rejected(screening_state, payload):
    with pytest.raises((InputInterruptionError, ValidationError)):
        resume_missing_input(_waiting(screening_state), payload)


@pytest.mark.parametrize("extra", ["score", "revision", "status", "required_inputs_missing"])
def test_resume_cannot_overwrite_authoritative_fields(screening_state, extracted_blocks, extra):
    payload = _payload(screening_state, extracted_blocks)
    payload[extra] = None
    with pytest.raises(ValidationError, match="Extra inputs"):
        resume_missing_input(_waiting(screening_state), payload)


def test_resume_rejects_wrong_identity_and_stale_extraction(screening_state, extracted_blocks):
    payload = _payload(screening_state, extracted_blocks)
    payload["screening_input"]["screening_id"] = "other"
    with pytest.raises(InputInterruptionError, match="screening_id"):
        resume_missing_input(_waiting(screening_state), payload)
    payload = _payload(screening_state, extracted_blocks)
    payload["screening_input"]["jd"]["input_id"] = "replacement-jd"
    with pytest.raises(ValueError, match="does not reference"):
        resume_missing_input(_waiting(screening_state), payload)


def test_replacement_metadata_is_validated(screening_state, extracted_blocks):
    payload = _payload(screening_state, extracted_blocks)
    payload["screening_input"]["jd"]["filename"] = " "
    result, _ = from_orchestration_state(resume_missing_input(_waiting(screening_state), payload))
    assert result.required_inputs_missing == ("jd.filename",)
    assert result.status is WorkflowStatus.WAITING_FOR_INPUT


def test_real_langgraph_interrupt_partial_resume_and_reconstruction(
    screening_state, extracted_blocks
):
    saver = InMemorySaver()  # Test-only backend, never selected by production code.
    graph = _graph(saver)
    config = {"configurable": {"thread_id": "screening-1"}}
    initial = to_orchestration_state(screening_state, extracted_blocks=())
    result = graph.invoke(initial, config)
    notice = result["__interrupt__"][0].value
    assert notice == {
        "screening_id": "screening-1",
        "current_node": "validate_input",
        "status": "waiting_for_input",
        "revision": 7,
        "required_inputs_missing": ["jd.extracted_content", "resume.extracted_content"],
    }
    snapshot = graph.get_state(config)
    state, _ = from_orchestration_state(snapshot.values)
    assert state.status is WorkflowStatus.WAITING_FOR_INPUT
    assert state.revision == 7
    assert snapshot.next == ("interrupt",)
    partial = graph.invoke(Command(resume=_payload(screening_state, extracted_blocks[:1])), config)
    assert partial["__interrupt__"][0].value["required_inputs_missing"] == [
        "resume.extracted_content"
    ]
    # Recompile over saved checkpoints; previous replies must replay correctly.
    graph = _graph(saver)
    result = graph.invoke(Command(resume=_payload(screening_state, extracted_blocks)), config)
    assert "__interrupt__" not in result
    state, blocks = from_orchestration_state(result)
    assert state == screening_state.model_copy(update={"status": WorkflowStatus.EVALUATING})
    assert blocks == extracted_blocks
    assert graph.get_state(config).next == ()
    assert initial == to_orchestration_state(screening_state, extracted_blocks=())


def test_real_langgraph_complete_inputs_do_not_interrupt(screening_state, extracted_blocks):
    graph = _graph(InMemorySaver())
    config = {"configurable": {"thread_id": "complete"}}
    transport = to_orchestration_state(screening_state, extracted_blocks=extracted_blocks)
    assert graph.invoke(transport, config) == transport


def test_real_langgraph_wrong_resume_fails_without_advancing(screening_state, extracted_blocks):
    graph = _graph(InMemorySaver())
    config = {"configurable": {"thread_id": "screening-1"}}
    graph.invoke(to_orchestration_state(screening_state, extracted_blocks=()), config)
    payload = _payload(screening_state, extracted_blocks)
    payload["screening_input"]["screening_id"] = "other"
    with pytest.raises(InputInterruptionError, match="screening_id"):
        graph.invoke(Command(resume=payload), config)
    state, _ = from_orchestration_state(graph.get_state(config).values)
    assert state.status is WorkflowStatus.WAITING_FOR_INPUT
    assert state.score == screening_state.score


def test_unrelated_missing_input_cannot_be_cleared_by_resume(screening_state, extracted_blocks):
    state = screening_state.model_copy(update={"required_inputs_missing": ("other.required",)})
    graph = _graph(InMemorySaver())
    config = {"configurable": {"thread_id": "unrelated"}}
    graph.invoke(to_orchestration_state(state, extracted_blocks=()), config)
    result = graph.invoke(Command(resume=_payload(state, extracted_blocks)), config)
    assert result["__interrupt__"][0].value["required_inputs_missing"] == ["other.required"]
    saved, _ = from_orchestration_state(graph.get_state(config).values)
    assert saved.status is WorkflowStatus.WAITING_FOR_INPUT
    # Verify the actual pause across another invocation, rather than relying on
    # snapshot.next while LangGraph has pending resume writes for the same task.
    again = graph.invoke(Command(resume=_payload(state, extracted_blocks)), config)
    assert again["__interrupt__"][0].value["required_inputs_missing"] == ["other.required"]


def test_domain_checkpoint_with_nonwaiting_state_is_rejected(screening_state):
    checkpoint = create_input_checkpoint(_waiting(screening_state))
    checkpoint = checkpoint.model_copy(update={"state": screening_state})
    with pytest.raises(InputInterruptionError, match="requires WAITING_FOR_INPUT"):
        restore_input_checkpoint(
            checkpoint, screening_id=screening_state.screening_id, extracted_blocks=()
        )


def test_restored_partial_checkpoint_retains_extraction(screening_state, extracted_blocks):
    partial = resume_missing_input(
        _waiting(screening_state), _payload(screening_state, extracted_blocks[:1])
    )
    checkpoint = create_input_checkpoint(partial)
    restored = restore_input_checkpoint(
        checkpoint, screening_id=screening_state.screening_id, extracted_blocks=extracted_blocks[:1]
    )
    assert restored == partial


def test_resume_can_correct_blank_metadata_without_losing_results(
    screening_state, extracted_blocks
):
    blank_input = screening_state.screening_input.model_copy(
        update={
            "jd": screening_state.screening_input.jd.model_copy(update={"filename": " "}),
        }
    )
    blank_state = screening_state.model_copy(update={"screening_input": blank_input})
    waiting = validate_input_state(
        to_orchestration_state(blank_state, extracted_blocks=extracted_blocks)
    )
    assert from_orchestration_state(waiting)[0].required_inputs_missing == ("jd.filename",)
    result, _ = from_orchestration_state(
        resume_missing_input(
            waiting,
            _payload(screening_state, extracted_blocks),
        )
    )
    assert result == screening_state.model_copy(update={"status": WorkflowStatus.EVALUATING})
