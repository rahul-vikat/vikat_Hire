from __future__ import annotations

from vikat_hire.contracts.evidence import EvidenceBundle
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.evidence import (
    EvidenceAssemblyError,
    assemble_evidence,
)


class EvidenceAssemblyNodeError(ValueError):
    """Raised when evidence-assembly orchestration input is invalid."""


def assemble_evidence_node(
    state: ScreeningState,
) -> ScreeningState:
    """
    Validate and assemble the evidence already present in ScreeningState.

    The node deliberately does not add an EvidenceBundle to persistent state.
    Claims, provenance, evidence, and reconciliation remain the authoritative
    state fields.

    The node does not:
    - fetch external evidence;
    - create evidence;
    - resolve contradictions;
    - evaluate dimensions;
    - calculate scores;
    - apply policy;
    - interpret LLM proposals.
    """

    if not isinstance(state, ScreeningState):
        raise EvidenceAssemblyNodeError(
            "state must be a ScreeningState"
        )

    try:
        bundle = assemble_evidence(
            claims=state.claims,
            provenances=state.provenances,
            evidence=state.evidence,
            reconciliations=state.reconciliations,
        )
    except EvidenceAssemblyError as exc:
        raise EvidenceAssemblyNodeError(str(exc)) from exc

    if not isinstance(bundle, EvidenceBundle):
        raise EvidenceAssemblyNodeError(
            "evidence assembly must return an EvidenceBundle"
        )

    evidence_ids = {
        item.evidence_id
        for item in state.evidence
    }

    if set(bundle.evidence_refs) != evidence_ids:
        raise EvidenceAssemblyNodeError(
            "assembled evidence references do not match state evidence"
        )

    if len(bundle.evidence_refs) != len(state.evidence):
        raise EvidenceAssemblyNodeError(
            "assembled evidence references are incomplete"
        )

    return state