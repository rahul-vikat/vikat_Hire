from __future__ import annotations

from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.normalization import NormalizationResult
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.state import (
    OrchestrationState,
    from_orchestration_state,
    to_orchestration_state,
)


_EXTERNAL_SOURCE_TYPES = frozenset(
    {
        SourceType.LINKEDIN,
        SourceType.GITHUB,
        SourceType.PORTFOLIO,
    }
)


class ApplyExternalNormalizationNodeError(ValueError):
    """Raised when external normalization cannot be applied."""


def apply_external_normalization_node(
    transport: OrchestrationState,
    *,
    normalization: NormalizationResult,
) -> OrchestrationState:
    """
    Materialize externally normalized candidate claims into ScreeningState.

    Collection has already attached the authoritative Provenance objects to
    ScreeningState. This node therefore copies only normalized Claim objects.

    It does not:
    - create provenance;
    - create evidence;
    - reconcile contradictions;
    - perform JD matching;
    - perform semantic evaluation;
    - evaluate seniority;
    - evaluate suitability;
    - calculate dimensions;
    - calculate scores;
    - apply policy;
    - interpret LLM output.
    """

    try:
        state, blocks, existing_normalization = from_orchestration_state(
            transport
        )
    except Exception as exc:
        raise ApplyExternalNormalizationNodeError(
            f"invalid orchestration state: {exc}"
        ) from exc

    if not isinstance(state, ScreeningState):
        raise ApplyExternalNormalizationNodeError(
            "transport must contain a ScreeningState"
        )

    if not isinstance(normalization, NormalizationResult):
        raise ApplyExternalNormalizationNodeError(
            "normalization must be a NormalizationResult"
        )

    if normalization.screening_id != state.screening_id:
        raise ApplyExternalNormalizationNodeError(
            "external normalization screening_id does not match "
            "state.screening_id"
        )

    if existing_normalization is not None:
        if existing_normalization.screening_id != state.screening_id:
            raise ApplyExternalNormalizationNodeError(
                "existing normalization screening_id does not match "
                "state.screening_id"
            )

    _validate_external_normalization(
        normalization=normalization,
        blocks=blocks,
    )

    normalized_claims = tuple(
        item.claim
        for item in normalization.claims
    )

    existing_claim_ids = {
        claim.claim_id
        for claim in state.claims
    }

    duplicate_existing_claim_ids = {
        claim.claim_id
        for claim in normalized_claims
        if claim.claim_id in existing_claim_ids
    }

    if duplicate_existing_claim_ids:
        raise ApplyExternalNormalizationNodeError(
            "external normalized claims already exist in screening state: "
            f"{sorted(duplicate_existing_claim_ids)}"
        )

    claim_ids: set[str] = set()

    for claim in normalized_claims:
        if claim.claim_id in claim_ids:
            raise ApplyExternalNormalizationNodeError(
                "external normalization contains duplicate claim id: "
                f"{claim.claim_id}"
            )

        claim_ids.add(claim.claim_id)

    updated_state = state.model_copy(
        update={
            "claims": (
                *state.claims,
                *normalized_claims,
            ),
        }
    )

    return to_orchestration_state(
        updated_state,
        extracted_blocks=blocks,
        normalization=existing_normalization,
    )


def _validate_external_normalization(
    *,
    normalization: NormalizationResult,
    blocks: tuple,
) -> None:
    block_ids = {
        block.block_id
        for block in blocks
    }

    for normalized_claim in normalization.claims:
        if normalized_claim.source_type not in _EXTERNAL_SOURCE_TYPES:
            raise ApplyExternalNormalizationNodeError(
                "external normalization contains a non-external claim source: "
                f"{normalized_claim.source_type.value!r}"
            )

        if not normalized_claim.source_ref.strip():
            raise ApplyExternalNormalizationNodeError(
                "external normalized claim source_ref must not be blank"
            )

        if not normalized_claim.claim.provenance_refs:
            raise ApplyExternalNormalizationNodeError(
                "external normalized claim must contain provenance references: "
                f"{normalized_claim.claim.claim_id}"
            )

        if not set(normalized_claim.provenance_refs).issubset(
            set(normalized_claim.claim.provenance_refs)
        ):
            raise ApplyExternalNormalizationNodeError(
                "normalized claim provenance_refs must be represented on "
                "the underlying Claim: "
                f"{normalized_claim.claim.claim_id}"
            )

        matching_blocks = tuple(
            block
            for block in blocks
            if block.source_type is normalized_claim.source_type
            and block.source_ref == normalized_claim.source_ref
        )

        if not matching_blocks:
            raise ApplyExternalNormalizationNodeError(
                "external normalized claim references a source without "
                "an extracted block: "
                f"{normalized_claim.source_ref}"
            )

        referenced_block_ids = {
            block.block_id
            for block in matching_blocks
        }

        if not referenced_block_ids.intersection(block_ids):
            raise ApplyExternalNormalizationNodeError(
                "external normalized claim source is not present in "
                "orchestration extracted blocks: "
                f"{normalized_claim.source_ref}"
            )