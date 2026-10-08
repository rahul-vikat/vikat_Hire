from __future__ import annotations

import pytest

from vikat_hire.collection.portfolio import PortfolioCollector
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
from vikat_hire.orchestration.nodes.collect_portfolio import (
    PortfolioCollectionNodeError,
    collect_portfolio_node,
)
from vikat_hire.orchestration.state import to_orchestration_state


class FakeFetcher:
    def __init__(self, text: str = "Portfolio evidence") -> None:
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
        current_node="collect_portfolio",
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
                portfolio_url="https://example.com/portfolio",
            ),
        ),
        required_inputs_missing=required_inputs_missing,
    )


def _transport(state: ScreeningState):
    return to_orchestration_state(
        state,
        extracted_blocks=(),
    )


def test_collect_portfolio_attaches_provenance_and_blocks() -> None:
    state = _state()
    fetcher = FakeFetcher()
    collector = PortfolioCollector(fetcher)

    result = collect_portfolio_node(
        _transport(state),
        collector=collector,
    )

    assert len(result["screening_state"]["provenances"]) == 1
    assert len(result["extracted_blocks"]) == 1

    provenance = result["screening_state"]["provenances"][0]
    block = result["extracted_blocks"][0]

    assert provenance["source_type"] == SourceType.PORTFOLIO
    assert block["source_type"] == SourceType.PORTFOLIO
    assert block["text"] == "Portfolio evidence"


def test_collect_portfolio_preserves_existing_provenance_and_blocks() -> None:
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

    result = collect_portfolio_node(
        transport,
        collector=PortfolioCollector(FakeFetcher()),
    )

    assert len(result["screening_state"]["provenances"]) == 2
    assert len(result["extracted_blocks"]) == 2
    assert result["extracted_blocks"][0]["block_id"] == "existing-block"


def test_collect_portfolio_does_not_fetch_when_not_authorized() -> None:
    state = _state(
        external_sources=ExternalSourceInput(
            portfolio_url="https://example.com/portfolio",
            portfolio_authorized=False,
        ),
    )

    fetcher = FakeFetcher()

    result = collect_portfolio_node(
        _transport(state),
        collector=PortfolioCollector(fetcher),
    )

    assert fetcher.calls == []
    assert len(result["screening_state"]["provenances"]) == 1
    assert result["extracted_blocks"] == []


def test_collect_portfolio_does_not_fetch_when_url_missing() -> None:
    state = _state(
        external_sources=ExternalSourceInput(),
    )

    fetcher = FakeFetcher()

    result = collect_portfolio_node(
        _transport(state),
        collector=PortfolioCollector(fetcher),
    )

    assert fetcher.calls == []
    assert result["screening_state"]["provenances"] == ()
    assert result["extracted_blocks"] == []


def test_collect_portfolio_rejects_waiting_for_input() -> None:
    state = _state(
        status=WorkflowStatus.WAITING_FOR_INPUT,
    )

    with pytest.raises(
        PortfolioCollectionNodeError,
        match="required input must be resolved",
    ):
        collect_portfolio_node(
            _transport(state),
            collector=PortfolioCollector(FakeFetcher()),
        )


def test_collect_portfolio_rejects_missing_required_input() -> None:
    state = _state(
        required_inputs_missing=("portfolio_authorization",),
    )

    with pytest.raises(
        PortfolioCollectionNodeError,
        match="required input must be resolved",
    ):
        collect_portfolio_node(
            _transport(state),
            collector=PortfolioCollector(FakeFetcher()),
        )


def test_collect_portfolio_rejects_failed_workflow() -> None:
    state = _state(
        status=WorkflowStatus.FAILED,
    )

    with pytest.raises(
        PortfolioCollectionNodeError,
        match="failed workflow",
    ):
        collect_portfolio_node(
            _transport(state),
            collector=PortfolioCollector(FakeFetcher()),
        )


def test_collect_portfolio_requires_portfolio_collector() -> None:
    with pytest.raises(
        PortfolioCollectionNodeError,
        match="must be a PortfolioCollector",
    ):
        collect_portfolio_node(
            _transport(_state()),
            collector=object(),  # type: ignore[arg-type]
        )


def test_collect_portfolio_preserves_workflow_fields() -> None:
    state = _state(
        status=WorkflowStatus.COLLECTING,
    )

    result = collect_portfolio_node(
        _transport(state),
        collector=PortfolioCollector(FakeFetcher()),
    )

    restored = ScreeningState.model_validate(
        result["screening_state"],
    )

    assert restored.screening_id == state.screening_id
    assert restored.status is WorkflowStatus.COLLECTING
    assert restored.current_node == state.current_node
    assert restored.revision == state.revision