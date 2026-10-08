from __future__ import annotations

import pytest

from vikat_hire.collection.linkedin import LinkedInCollector
from vikat_hire.contracts.common import (
    AccessStatus,
    DerivationMethod,
    Provenance,
    SourceType,
    WorkflowStatus,
)
from vikat_hire.contracts.inputs import (
    DocumentInput,
    ExternalSourceInput,
    ScreeningInput,
)
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    ExtractionKind,
)
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.nodes.collect_linkedin import (
    LinkedInCollectionNodeError,
    collect_linkedin_node,
)
from vikat_hire.orchestration.state import to_orchestration_state


class FakeFetcher:
    def __init__(self, text: str = "LinkedIn evidence") -> None:
        self.text = text
        self.calls: list[str] = []

    def fetch(self, *, url: str) -> str:
        self.calls.append(url)
        return self.text


def _state(
    *,
    external_sources: ExternalSourceInput | None = None,
    status: WorkflowStatus = WorkflowStatus.CREATED,
    required_inputs_missing: tuple[str, ...] = (),
) -> ScreeningState:
    screening_id = "screening-1"

    return ScreeningState(
        screening_id=screening_id,
        status=status,
        current_node="evaluate_linkedin",
        screening_input=ScreeningInput(
            screening_id=screening_id,
            jd=DocumentInput(
                kind="jd",
                filename="jd.pdf",
                media_type="application/pdf",
                content_hash="jd-hash",
                storage_ref="jd-storage",
            ),
            resume=DocumentInput(
                kind="resume",
                filename="resume.pdf",
                media_type="application/pdf",
                content_hash="resume-hash",
                storage_ref="resume-storage",
            ),
            external_sources=external_sources
            or ExternalSourceInput(
                linkedin_url="https://www.linkedin.com/in/example",
            ),
        ),
        required_inputs_missing=required_inputs_missing,
    )


def _transport(state: ScreeningState):
    return to_orchestration_state(
        state,
        extracted_blocks=(),
    )


def test_collect_linkedin_attaches_provenance_and_blocks() -> None:
    state = _state()
    fetcher = FakeFetcher()
    collector = LinkedInCollector(fetcher)

    result = collect_linkedin_node(
        _transport(state),
        collector=collector,
    )

    assert len(result["screening_state"]["provenances"]) == 1
    assert len(result["extracted_blocks"]) == 1

    provenance = result["screening_state"]["provenances"][0]
    block = result["extracted_blocks"][0]

    assert provenance["source_type"] == SourceType.LINKEDIN
    assert block["source_type"] == SourceType.LINKEDIN
    assert block["text"] == "LinkedIn evidence"


def test_collect_linkedin_preserves_existing_provenance_and_blocks() -> None:
    state = _state()

    existing_provenance = Provenance(
        provenance_id="existing-prov",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        method=DerivationMethod.PARSER,
        access_status=AccessStatus.AUTHORIZED,
    )

    existing_block = ExtractedTextBlock(
        block_id="existing-block",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-1",
        text="Existing resume evidence",
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=("existing-prov",),
    )

    state = state.model_copy(
        update={
            "provenances": (existing_provenance,),
        }
    )

    transport = to_orchestration_state(
        state,
        extracted_blocks=(existing_block,),
    )

    result = collect_linkedin_node(
        transport,
        collector=LinkedInCollector(FakeFetcher()),
    )

    assert len(result["screening_state"]["provenances"]) == 2
    assert len(result["extracted_blocks"]) == 2
    assert result["extracted_blocks"][0]["block_id"] == "existing-block"


def test_collect_linkedin_does_not_fetch_when_not_authorized() -> None:
    state = _state(
        external_sources=ExternalSourceInput(
            linkedin_url="https://www.linkedin.com/in/example",
            linkedin_authorized=False,
        ),
    )

    fetcher = FakeFetcher()

    result = collect_linkedin_node(
        _transport(state),
        collector=LinkedInCollector(fetcher),
    )

    assert fetcher.calls == []
    assert len(result["screening_state"]["provenances"]) == 1
    assert result["extracted_blocks"] == []


def test_collect_linkedin_does_not_fetch_when_url_missing() -> None:
    state = _state(
        external_sources=ExternalSourceInput(),
    )

    fetcher = FakeFetcher()

    result = collect_linkedin_node(
        _transport(state),
        collector=LinkedInCollector(fetcher),
    )

    assert fetcher.calls == []
    assert result["screening_state"]["provenances"] == ()
    assert result["extracted_blocks"] == []


def test_collect_linkedin_rejects_waiting_for_input() -> None:
    state = _state(
        status=WorkflowStatus.WAITING_FOR_INPUT,
    )

    with pytest.raises(
        LinkedInCollectionNodeError,
        match="required input must be resolved",
    ):
        collect_linkedin_node(
            _transport(state),
            collector=LinkedInCollector(FakeFetcher()),
        )


def test_collect_linkedin_rejects_missing_required_input() -> None:
    state = _state(
        required_inputs_missing=("linkedin_authorization",),
    )

    with pytest.raises(
        LinkedInCollectionNodeError,
        match="required input must be resolved",
    ):
        collect_linkedin_node(
            _transport(state),
            collector=LinkedInCollector(FakeFetcher()),
        )


def test_collect_linkedin_rejects_failed_workflow() -> None:
    state = _state(
        status=WorkflowStatus.FAILED,
    )

    with pytest.raises(
        LinkedInCollectionNodeError,
        match="failed workflow",
    ):
        collect_linkedin_node(
            _transport(state),
            collector=LinkedInCollector(FakeFetcher()),
        )


def test_collect_linkedin_requires_linkedin_collector() -> None:
    with pytest.raises(
        LinkedInCollectionNodeError,
        match="must be a LinkedInCollector",
    ):
        collect_linkedin_node(
            _transport(_state()),
            collector=object(),  # type: ignore[arg-type]
        )


def test_collect_linkedin_preserves_workflow_fields() -> None:
    state = _state(
        status=WorkflowStatus.COLLECTING,
    )

    result = collect_linkedin_node(
        _transport(state),
        collector=LinkedInCollector(FakeFetcher()),
    )

    restored = ScreeningState.model_validate(
        result["screening_state"],
    )

    assert restored.screening_id == state.screening_id
    assert restored.status is WorkflowStatus.COLLECTING
    assert restored.current_node == state.current_node
    assert restored.revision == state.revision