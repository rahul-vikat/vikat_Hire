from __future__ import annotations

from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.state import (
    OrchestrationState,
    from_orchestration_state,
)


class ApplyNormalizationNodeError(ValueError):
    """Raised when normalized data cannot be applied to screening state."""


def apply_normalization_node(
    transport: OrchestrationState,
) -> OrchestrationState:
    """
    Materialize normalized candidate claims into ScreeningState.

    This node is an orchestration boundary only.

    It does not:
    - perform JD matching;
    - perform semantic evaluation;
    - evaluate seniority;
    - evaluate suitability;
    - calculate dimensions;
    - calculate scores;
    - apply policy;
    - interpret LLM output.

    Normalization remains the authoritative source of the factual claims.
    """

    try:
        state, blocks, normalization = from_orchestration_state(
            transport
        )
    except Exception as exc:
        raise ApplyNormalizationNodeError(
            f"invalid orchestration state: {exc}"
        ) from exc

    if not isinstance(state, ScreeningState):
        raise ApplyNormalizationNodeError(
            "transport must contain a ScreeningState"
        )

    if normalization is None:
        raise ApplyNormalizationNodeError(
            "cannot apply normalization before normalization is available"
        )

    if normalization.screening_id != state.screening_id:
        raise ApplyNormalizationNodeError(
            "normalization screening_id does not match state.screening_id"
        )

    normalized_claims = tuple(
        normalized_claim.claim
        for normalized_claim in normalization.claims
    )

    existing_claim_ids = {
        claim.claim_id
        for claim in state.claims
    }

    duplicate_claim_ids = (
        {
            claim.claim_id
            for claim in normalized_claims
            if claim.claim_id in existing_claim_ids
        }
    )

    if duplicate_claim_ids:
        raise ApplyNormalizationNodeError(
            "normalized claims already exist in screening state: "
            f"{sorted(duplicate_claim_ids)}"
        )

    normalized_claim_id_counts: dict[str, int] = {}

    for claim in normalized_claims:
        normalized_claim_id_counts[claim.claim_id] = (
            normalized_claim_id_counts.get(claim.claim_id, 0) + 1
        )

    duplicate_normalized_claim_ids = {
        claim_id
        for claim_id, count in normalized_claim_id_counts.items()
        if count > 1
    }

    if duplicate_normalized_claim_ids:
        raise ApplyNormalizationNodeError(
            "normalization contains duplicate claim ids: "
            f"{sorted(duplicate_normalized_claim_ids)}"
        )

    updated_state = state.model_copy(
        update={
            "claims": (
                *state.claims,
                *normalized_claims,
            ),
        }
    )

    return {
        **transport,
        "screening_state": updated_state.model_dump(
            mode="python"
        ),
        "extracted_blocks": [
            block.model_dump(mode="python")
            for block in blocks
        ],
        "normalization": normalization.model_dump(
            mode="python"
        ),
    }