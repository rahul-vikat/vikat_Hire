from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from vikat_hire.contracts.common import ReviewReason, WorkflowStatus
from vikat_hire.contracts.policy import ReviewRequest
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.state import (
    OrchestrationStateError,
    from_orchestration_state,
    to_orchestration_state,
)


def test_roundtrip_preserves_all_domain_fields_and_extraction(screening_state, extracted_blocks):
    transport = to_orchestration_state(screening_state, extracted_blocks=extracted_blocks)
    state, blocks, normalization = from_orchestration_state(transport)
    assert state == screening_state
    assert blocks == extracted_blocks
    assert normalization is None
    assert state.score.score == Decimal("74.94")
    assert isinstance(state.evidence[0].content["nested"]["value"], Decimal)
    with pytest.raises(ValidationError):
        state.revision = 8


def test_transport_and_decoded_state_do_not_alias_original(screening_state, extracted_blocks):
    transport = to_orchestration_state(screening_state, extracted_blocks=extracted_blocks)
    state, _, normalization = from_orchestration_state(transport)
    assert normalization is None
    transport["screening_state"]["evidence"][0]["content"]["nested"]["value"] = 0
    state.provenances[0].locator["page"] = "changed"
    assert screening_state.evidence[0].content["nested"]["value"] == Decimal("12.34")
    assert state.evidence[0].content["nested"]["value"] == Decimal("12.34")
    assert screening_state.provenances[0].locator == {"page": "1"}
    assert transport["screening_state"]["provenances"][0]["locator"] == {"page": "1"}


@pytest.mark.parametrize(
    "artifact", ["screening_input", "evaluation", "score", "policy", "explanation"]
)
def test_identity_mismatch_rejected(screening_state, artifact):
    state = screening_state.model_copy(
        update={
            artifact: getattr(screening_state, artifact).model_copy(
                update={"screening_id": "other"}
            )
        }
    )
    with pytest.raises(OrchestrationStateError, match="screening_id does not match"):
        to_orchestration_state(state, extracted_blocks=())


@pytest.mark.parametrize(
    "transport",
    [
        None,
        {},
        {"screening_state": {}},
        {
            "screening_state": {},
            "extracted_blocks": [],
            "extra": True,
        },
        {"screening_state": None, "extracted_blocks": []},
        {
            "screening_state": {},
            "extracted_blocks": ["bad"],
        },
    ],
)
def test_invalid_transport_rejected(transport):
    with pytest.raises(OrchestrationStateError):
        from_orchestration_state(transport)


@pytest.mark.parametrize(
    "field,value",
    [("current_node", " "), ("screening_id", ""), ("required_inputs_missing", (" ",))],
)
def test_blank_workflow_identifiers_rejected(screening_state, field, value):
    with pytest.raises(OrchestrationStateError):
        to_orchestration_state(
            screening_state.model_copy(update={field: value}), extracted_blocks=()
        )


def test_unchecked_nested_model_copy_is_revalidated(screening_state, extracted_blocks):
    transport = to_orchestration_state(screening_state, extracted_blocks=extracted_blocks)
    invalid = deepcopy(transport)
    invalid["screening_state"]["screening_input"]["jd"] = None
    with pytest.raises(ValidationError):
        from_orchestration_state(invalid)
    invalid = deepcopy(transport)
    invalid["extracted_blocks"][0]["text"] = " "
    with pytest.raises(ValidationError):
        from_orchestration_state(invalid)


def test_invalid_domain_objects_rejected(screening_state):
    with pytest.raises(OrchestrationStateError):
        to_orchestration_state(None, extracted_blocks=())
    with pytest.raises(OrchestrationStateError):
        to_orchestration_state(screening_state, extracted_blocks=("bad",))


@pytest.mark.parametrize("field", list(ScreeningState.model_fields))
def test_incomplete_snapshot_cannot_reset_domain_fields(screening_state, field):
    transport = to_orchestration_state(screening_state, extracted_blocks=())
    del transport["screening_state"][field]
    with pytest.raises(OrchestrationStateError, match=f"snapshot is missing fields: {field}$"):
        from_orchestration_state(transport)


@pytest.mark.parametrize("status", list(WorkflowStatus))
@pytest.mark.parametrize("revision", [0, 7])
def test_roundtrip_preserves_workflow_and_nonempty_reviews(
    screening_state, extracted_blocks, status, revision
):
    review = ReviewRequest(
        reason=ReviewReason.CONTRADICTION,
        blocking=True,
        evidence_refs=("evidence-1",),
        contradiction_refs=("contradiction-1",),
        requested_action="Resolve conflicting evidence.",
    )
    state = screening_state.model_copy(
        update={
            "status": status,
            "revision": revision,
            "current_node": "review",
            "pending_reviews": (review,),
            "required_inputs_missing": ("jd.extracted_content", "other.required"),
            "errors": ("first diagnostic", "second diagnostic"),
        }
    )
    transport = to_orchestration_state(state, extracted_blocks=extracted_blocks)
    decoded, blocks, normalization = from_orchestration_state(transport)
    assert decoded == state
    assert blocks == extracted_blocks
    assert normalization is None
    assert decoded.pending_reviews == (review,)
    assert decoded.updated_at == state.updated_at
    # Conversion preserves state; it must not make routing or review decisions.
    assert decoded.status is status
    assert decoded.revision == revision


def test_conversion_is_repeatable_and_does_not_change_transport(screening_state, extracted_blocks):
    transport = to_orchestration_state(screening_state, extracted_blocks=extracted_blocks)
    original = deepcopy(transport)
    first_state, first_blocks, first_normalization = from_orchestration_state(transport)
    second_state, second_blocks, second_normalization = from_orchestration_state(transport)
    assert first_state == second_state == screening_state
    assert first_blocks == second_blocks == extracted_blocks
    assert first_normalization is second_normalization is None
    assert transport == original
    assert to_orchestration_state(first_state, extracted_blocks=first_blocks) == original
