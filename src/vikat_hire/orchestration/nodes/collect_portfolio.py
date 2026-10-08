from __future__ import annotations

from vikat_hire.collection.external import ExternalCollectionResult
from vikat_hire.collection.portfolio import PortfolioCollector
from vikat_hire.contracts.collection import CollectionStatus
from vikat_hire.contracts.common import SourceType, WorkflowStatus
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.state import (
    OrchestrationState,
    from_orchestration_state,
    to_orchestration_state,
)


class PortfolioCollectionNodeError(ValueError):
    """Invalid Portfolio collection node input or result."""


def collect_portfolio_node(
    transport: OrchestrationState,
    *,
    collector: PortfolioCollector,
) -> OrchestrationState:
    """
    Collect portfolio evidence through an injected provider.

    The node only attaches retrieval artifacts:
    - Provenance -> ScreeningState.provenances
    - ExtractedTextBlock -> orchestration transport

    It does not normalize, match, evaluate, score, or decide eligibility.
    """
    if not isinstance(collector, PortfolioCollector):
        raise PortfolioCollectionNodeError(
            "collector must be a PortfolioCollector"
        )

    state, existing_blocks, _ = from_orchestration_state(transport)

    _validate_state(state)

    result = collector.collect(
        source_input=state.screening_input.external_sources,
    )

    if not isinstance(result, ExternalCollectionResult):
        raise PortfolioCollectionNodeError(
            "Portfolio collector must return ExternalCollectionResult"
        )

    _validate_result(
        state=state,
        existing_blocks=existing_blocks,
        result=result,
    )

    updated_state = state.model_copy(
        update={
            "provenances": (
                *state.provenances,
                *result.provenances,
            ),
        }
    )

    return to_orchestration_state(
        updated_state,
        extracted_blocks=(
            *existing_blocks,
            *result.extracted_blocks,
        ),
    )


def _validate_state(state: ScreeningState) -> None:
    if not isinstance(state, ScreeningState):
        raise PortfolioCollectionNodeError(
            "state must be a ScreeningState"
        )

    if state.screening_input.screening_id != state.screening_id:
        raise PortfolioCollectionNodeError(
            "input screening_id does not match state"
        )

    if state.required_inputs_missing:
        raise PortfolioCollectionNodeError(
            "required input must be resolved before Portfolio collection"
        )

    if state.status is WorkflowStatus.WAITING_FOR_INPUT:
        raise PortfolioCollectionNodeError(
            "required input must be resolved before Portfolio collection"
        )

    if state.status is WorkflowStatus.FAILED:
        raise PortfolioCollectionNodeError(
            "cannot collect Portfolio evidence from failed workflow"
        )


def _validate_result(
    *,
    state: ScreeningState,
    existing_blocks: tuple,
    result: ExternalCollectionResult,
) -> None:
    if result.source.source_type is not SourceType.PORTFOLIO:
        raise PortfolioCollectionNodeError(
            "Portfolio collector returned a non-Portfolio source"
        )

    existing_provenance_ids = {
        provenance.provenance_id
        for provenance in state.provenances
    }

    duplicate_provenance_ids = existing_provenance_ids.intersection(
        provenance.provenance_id
        for provenance in result.provenances
    )

    if duplicate_provenance_ids:
        raise PortfolioCollectionNodeError(
            "Portfolio collection returned duplicate provenance IDs: "
            f"{sorted(duplicate_provenance_ids)}"
        )

    existing_block_ids = {
        block.block_id
        for block in existing_blocks
    }

    duplicate_block_ids = existing_block_ids.intersection(
        block.block_id
        for block in result.extracted_blocks
    )

    if duplicate_block_ids:
        raise PortfolioCollectionNodeError(
            "Portfolio collection returned duplicate block IDs: "
            f"{sorted(duplicate_block_ids)}"
        )

    source_input = state.screening_input.external_sources

    if result.source.status is CollectionStatus.COLLECTED:
        expected_source_ref = f"portfolio-{source_input.input_id}"

        if result.source.source_ref != expected_source_ref:
            raise PortfolioCollectionNodeError(
                "Portfolio source reference does not match external input identity"
            )

    if result.source.status is CollectionStatus.NOT_AUTHORIZED:
        if result.source.access_status is None:
            raise PortfolioCollectionNodeError(
                "Portfolio unauthorized result must contain an access status"
            )

        if result.source.access_status.value != "not_authorized":
            raise PortfolioCollectionNodeError(
                "Portfolio unauthorized result has invalid access status"
            )
