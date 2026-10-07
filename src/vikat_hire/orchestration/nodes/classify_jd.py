from hashlib import sha256

from vikat_hire.config.jd_classification import JDClassificationConfiguration
from vikat_hire.contracts.common import InputKind, SourceType, WorkflowStatus
from vikat_hire.contracts.normalization import NormalizationResult
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.evaluation.jd_classification import classify_jd_requirements


class JDClassificationNodeError(ValueError):
    """Classification input is malformed or belongs to another screening."""


def classify_jd_node(
    state: ScreeningState,
    *,
    normalization: NormalizationResult,
    configuration: JDClassificationConfiguration,
) -> ScreeningState:
    """Attach a classification or blocking review without scoring or routing.

    Empty extraction returns to the existing missing-input path. Ambiguous
    classification leaves classification unset so normal classification routing
    cannot proceed. Existing reviews and all prior results remain intact.
    """
    if not isinstance(state, ScreeningState):
        raise JDClassificationNodeError("state must be a ScreeningState")
    if not isinstance(normalization, NormalizationResult):
        raise JDClassificationNodeError("normalization must be a NormalizationResult")
    normalization = NormalizationResult.model_validate(normalization.model_dump())
    if normalization.screening_id != state.screening_id:
        raise JDClassificationNodeError("normalization screening_id does not match state")
    if state.screening_input.screening_id != state.screening_id:
        raise JDClassificationNodeError("input screening_id does not match state")
    if state.screening_input.jd.kind is not InputKind.JD:
        raise JDClassificationNodeError("JD document has incorrect kind")
    if state.required_inputs_missing or state.status is WorkflowStatus.WAITING_FOR_INPUT:
        raise JDClassificationNodeError("required input must be resolved before classification")
    blocks = {block.block_id: block for block in normalization.extracted_blocks}
    if len(blocks) != len(normalization.extracted_blocks):
        raise JDClassificationNodeError("duplicate extracted block IDs")
    jd_blocks = {
        key: block for key, block in blocks.items() if block.source_type is SourceType.JD_FILE
    }
    if any(block.source_ref != state.screening_input.jd.input_id for block in jd_blocks.values()):
        raise JDClassificationNodeError("JD block does not reference the input JD")
    if any(not ref.strip() for block in jd_blocks.values() for ref in block.provenance_refs):
        raise JDClassificationNodeError("JD block provenance references must not be blank")
    for requirement in normalization.jd_requirements:
        block = jd_blocks.get(requirement.source_ref)
        if block is None:
            raise JDClassificationNodeError("JD requirement does not reference a JD block")
        if not set(requirement.provenance_refs).issubset(block.provenance_refs):
            raise JDClassificationNodeError("JD requirement provenance does not match its block")
    if not jd_blocks:
        return state.model_copy(
            update={
                "classification": None,
                "status": WorkflowStatus.WAITING_FOR_INPUT,
                "required_inputs_missing": ("jd.extracted_content",),
            }
        )
    assessment = classify_jd_requirements(
        requirements=normalization.jd_requirements,
        configuration=configuration,
        created_at=state.updated_at,
    )
    updates = {"classification": assessment.classification}
    if assessment.review is not None:
        review_request = assessment.review
        if not normalization.jd_requirements:
            review_request = review_request.model_copy(
                update={
                    "review_id": "jd-classification-"
                    + sha256(
                        (
                            review_request.review_id
                            + "".join(jd_blocks[key].model_dump_json() for key in sorted(jd_blocks))
                        ).encode()
                    ).hexdigest(),
                    "evidence_refs": tuple(sorted(jd_blocks)),
                    "requested_action": review_request.requested_action
                    + "; JD block provenance="
                    + ",".join(
                        sorted(
                            {ref for block in jd_blocks.values() for ref in block.provenance_refs}
                        )
                    ),
                }
            )
        reviews = state.pending_reviews
        if not any(review.review_id == review_request.review_id for review in reviews):
            reviews = (*reviews, review_request)
        updates.update(status=WorkflowStatus.REVIEW_REQUIRED, pending_reviews=reviews)
    return state.model_copy(update=updates)
