import pytest
from pydantic import ValidationError

from vikat_hire.config.jd_classification import JDClassificationConfiguration
from vikat_hire.contracts.common import ReviewReason, SourceType, WorkflowStatus
from vikat_hire.contracts.normalization import NormalizationResult
from vikat_hire.contracts.policy import ReviewRequest
from vikat_hire.evaluation.jd_classification import classify_jd_requirements
from vikat_hire.normalization.document import extract_document_text
from vikat_hire.normalization.jd import normalize_jd
from vikat_hire.orchestration.nodes.classify_jd import classify_jd_node


@pytest.fixture
def configuration():
    return JDClassificationConfiguration(
        configuration_ref="test-rules-v1",
        technical_indicators=("Python", "Responsible for building software"),
        non_technical_indicators=("Payroll administration",),
    )


def _normalization(state, text):
    blocks = extract_document_text(
        document=state.screening_input.jd, content=text.encode(), provenance_refs=("jd-provenance",)
    )
    requirements, _, _ = normalize_jd(blocks=blocks, screening_id=state.screening_id)
    return NormalizationResult(
        screening_id=state.screening_id, extracted_blocks=blocks, jd_requirements=requirements
    )


@pytest.mark.parametrize(
    "text,label",
    [
        ("Required: Python", "technical"),
        ("Required: Payroll administration", "non_technical"),
        ("Required:   PYTHON  ", "technical"),
        ("Responsible for building software", "technical"),
    ],
)
def test_classifies_only_configured_jd_evidence(screening_state, configuration, text, label):
    result = classify_jd_node(
        screening_state,
        normalization=_normalization(screening_state, text),
        configuration=configuration,
    )
    assert result.classification.jd_type == label
    assert result.classification.provenance_refs == ("jd-provenance",)
    assert "test-rules-v1" in result.classification.rationale
    assert "requirements=" in result.classification.rationale
    for field in type(screening_state).model_fields:
        if field != "classification":
            assert getattr(result, field) == getattr(screening_state, field)


@pytest.mark.parametrize(
    "text",
    [
        "Required: communication",
        "Required: Not Python",
        "Required: Python and payroll",
        "Required: degree in Python",
        "Job title: Python",
        "Employer: Python",
        "Compensation: Python",
    ],
)
def test_unmatched_or_excluded_evidence_requires_review(screening_state, configuration, text):
    result = classify_jd_node(
        screening_state,
        normalization=_normalization(screening_state, text),
        configuration=configuration,
    )
    assert result.classification is None
    assert result.status is WorkflowStatus.REVIEW_REQUIRED
    review = result.pending_reviews[0]
    assert review.reason is ReviewReason.AMBIGUOUS_REQUIREMENT
    assert review.blocking
    assert review.evidence_refs
    assert "jd-provenance" in review.requested_action


def test_conflicting_indicators_preserve_evidence_and_prior_reviews(screening_state, configuration):
    prior = ReviewRequest(
        reason=ReviewReason.AUTHORIZATION, blocking=True, requested_action="Check authorization"
    )
    state = screening_state.model_copy(update={"pending_reviews": (prior,)})
    normalization = _normalization(state, "Required: Python\nRequired: Payroll administration")
    result = classify_jd_node(state, normalization=normalization, configuration=configuration)
    assert result.classification is None
    assert result.pending_reviews[0] == prior
    assert result.pending_reviews[1].reason is ReviewReason.CONTRADICTION
    assert len(result.pending_reviews[1].evidence_refs) == 2
    assert result.score == state.score
    assert (
        classify_jd_node(result, normalization=normalization, configuration=configuration) == result
    )


def test_empty_extraction_returns_to_input_wait(screening_state, configuration):
    result = classify_jd_node(
        screening_state,
        normalization=NormalizationResult(screening_id=screening_state.screening_id),
        configuration=configuration,
    )
    assert result.classification is None
    assert result.status is WorkflowStatus.WAITING_FOR_INPUT
    assert result.required_inputs_missing == ("jd.extracted_content",)
    assert result.score == screening_state.score
    assert result.revision == screening_state.revision


def test_repeatable_classification_and_order_independence(screening_state, configuration):
    normalization = _normalization(
        screening_state, "Required: Python\nResponsible for building software"
    )
    first = classify_jd_node(
        screening_state, normalization=normalization, configuration=configuration
    )
    reversed_input = normalization.model_copy(
        update={"jd_requirements": tuple(reversed(normalization.jd_requirements))}
    )
    second = classify_jd_node(
        screening_state, normalization=reversed_input, configuration=configuration
    )
    assert first == second


@pytest.mark.parametrize("change", ["identity", "source", "provenance", "duplicate", "candidate"])
def test_malformed_jd_evidence_fails(screening_state, configuration, change):
    normalized = _normalization(screening_state, "Required: Python")
    requirement = normalized.jd_requirements[0]
    if change == "identity":
        normalized = normalized.model_copy(update={"screening_id": "other"})
    elif change == "duplicate":
        normalized = normalized.model_copy(update={"jd_requirements": (requirement, requirement)})
    else:
        updates = {
            "source": {"source_ref": "other"},
            "provenance": {"provenance_refs": ("other",)},
            "candidate": {"source_type": SourceType.RESUME_FILE},
        }[change]
        normalized = normalized.model_copy(
            update={"jd_requirements": (requirement.model_copy(update=updates),)}
        )
    with pytest.raises(ValueError):
        classify_jd_node(screening_state, normalization=normalized, configuration=configuration)


def test_waiting_state_cannot_be_classified(screening_state, configuration):
    state = screening_state.model_copy(
        update={"required_inputs_missing": ("resume.extracted_content",)}
    )
    with pytest.raises(ValueError, match="required input"):
        classify_jd_node(
            state,
            normalization=_normalization(state, "Required: Python"),
            configuration=configuration,
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"technical_indicators": ()},
        {"technical_indicators": (" ",)},
        {"technical_indicators": ("Python", " PYTHON ")},
        {"non_technical_indicators": ("python",)},
        {"configuration_ref": " "},
    ],
)
def test_invalid_configuration_rejected(configuration, updates):
    with pytest.raises(ValidationError):
        JDClassificationConfiguration.model_validate({**configuration.model_dump(), **updates})


def test_configuration_is_required_and_immutable(configuration):
    with pytest.raises(ValidationError):
        JDClassificationConfiguration(configuration_ref="rules")
    with pytest.raises(ValidationError):
        configuration.configuration_ref = "changed"


def test_pure_classifier_rejects_invalid_objects(screening_state, configuration):
    with pytest.raises(ValueError, match="JDRequirement"):
        classify_jd_requirements(
            requirements=("bad",),
            configuration=configuration,
            created_at=screening_state.updated_at,
        )
    with pytest.raises(ValueError, match="JDClassificationConfiguration"):
        classify_jd_requirements(
            requirements=(), configuration=None, created_at=screening_state.updated_at
        )


def test_candidate_content_does_not_change_classification(
    screening_state, extracted_blocks, configuration
):
    normalized = _normalization(screening_state, "Required: Payroll administration")
    baseline = classify_jd_node(
        screening_state, normalization=normalized, configuration=configuration
    )
    mixed = normalized.model_copy(
        update={
            "extracted_blocks": (
                *normalized.extracted_blocks,
                extracted_blocks[1].model_copy(update={"text": "Python"}),
            )
        }
    )
    assert (
        classify_jd_node(screening_state, normalization=mixed, configuration=configuration)
        == baseline
    )


def test_unstructured_reviews_are_repeatable_and_specific_to_jd(screening_state, configuration):
    normalized = _normalization(screening_state, "Unstructured JD description")
    first = classify_jd_node(screening_state, normalization=normalized, configuration=configuration)
    assert classify_jd_node(first, normalization=normalized, configuration=configuration) == first
    different = classify_jd_node(
        screening_state,
        normalization=_normalization(screening_state, "Different unstructured JD"),
        configuration=configuration,
    )
    assert first.pending_reviews[0].review_id != different.pending_reviews[0].review_id


@pytest.mark.parametrize(
    "change", ["blank_provenance", "wrong_document", "duplicate_blocks", "blank_text"]
)
def test_invalid_extraction_fails(screening_state, configuration, change):
    normalized = _normalization(screening_state, "Description")
    block = normalized.extracted_blocks[0]
    if change == "duplicate_blocks":
        blocks = (block, block)
    else:
        updates = {
            "blank_provenance": {"provenance_refs": (" ",)},
            "wrong_document": {"source_ref": "other-jd"},
            "blank_text": {"text": " "},
        }[change]
        blocks = (block.model_copy(update=updates),)
    with pytest.raises(ValueError):
        classify_jd_node(
            screening_state,
            normalization=normalized.model_copy(update={"extracted_blocks": blocks}),
            configuration=configuration,
        )


def test_invalid_node_arguments_fail(screening_state, configuration):
    with pytest.raises(ValueError, match="state must"):
        classify_jd_node(None, normalization=None, configuration=configuration)
    with pytest.raises(ValueError, match="normalization must"):
        classify_jd_node(screening_state, normalization=None, configuration=configuration)
