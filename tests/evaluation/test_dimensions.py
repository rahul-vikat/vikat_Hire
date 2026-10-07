from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
)
from vikat_hire.evaluation.dimensions import (
    DimensionEvaluationError,
    assemble_evaluation_result,
    evaluate_dimension,
)


def test_evaluated_dimension_preserves_authoritative_value_and_refs() -> None:
    evaluation = evaluate_dimension(
        dimension=DimensionName.MUST_HAVE_COVERAGE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("87.50"),
        evidence_refs=("evidence-1",),
        requirement_refs=("requirement-1",),
        provenance_refs=("provenance-1",),
        rationale="Deterministic must-have coverage was evaluated.",
    )

    assert evaluation.dimension is DimensionName.MUST_HAVE_COVERAGE
    assert evaluation.applicability is ApplicabilityStatus.APPLICABLE
    assert evaluation.resolution is DimensionResolution.EVALUATED
    assert evaluation.raw_value == Decimal("87.50")
    assert evaluation.evidence_refs == ("evidence-1",)
    assert evaluation.requirement_refs == ("requirement-1",)
    assert evaluation.provenance_refs == ("provenance-1",)
    assert evaluation.exclusion_reason is None


def test_applicable_dimension_can_be_excluded_for_insufficient_evidence() -> None:
    evaluation = evaluate_dimension(
        dimension=DimensionName.LINKEDIN_EVIDENCE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EXCLUDED,
        exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
        provenance_refs=("provenance-1",),
        rationale="LinkedIn evidence was insufficient for evaluation.",
    )

    assert evaluation.applicability is ApplicabilityStatus.APPLICABLE
    assert evaluation.resolution is DimensionResolution.EXCLUDED
    assert evaluation.raw_value is None
    assert (
        evaluation.exclusion_reason
        is ExclusionReason.INSUFFICIENT_EVIDENCE
    )


def test_not_applicable_dimension_is_excluded() -> None:
    evaluation = evaluate_dimension(
        dimension=DimensionName.GITHUB_EVIDENCE,
        applicability=ApplicabilityStatus.NOT_APPLICABLE,
        resolution=DimensionResolution.EXCLUDED,
        exclusion_reason=ExclusionReason.NOT_APPLICABLE,
        rationale="GitHub evidence is not applicable to this screening.",
    )

    assert evaluation.applicability is ApplicabilityStatus.NOT_APPLICABLE
    assert evaluation.resolution is DimensionResolution.EXCLUDED
    assert evaluation.raw_value is None
    assert evaluation.exclusion_reason is ExclusionReason.NOT_APPLICABLE


def test_not_applicable_dimension_cannot_be_evaluated() -> None:
    with pytest.raises(DimensionEvaluationError):
        evaluate_dimension(
            dimension=DimensionName.PORTFOLIO_EVIDENCE,
            applicability=ApplicabilityStatus.NOT_APPLICABLE,
            resolution=DimensionResolution.EVALUATED,
            raw_value=Decimal("100"),
            rationale="Invalid evaluated not-applicable dimension.",
        )


def test_evaluated_dimension_requires_raw_value() -> None:
    with pytest.raises(DimensionEvaluationError):
        evaluate_dimension(
            dimension=DimensionName.SEMANTIC_FIT,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EVALUATED,
            rationale="Missing deterministic raw value.",
        )


def test_evaluated_dimension_cannot_have_exclusion_reason() -> None:
    with pytest.raises(DimensionEvaluationError):
        evaluate_dimension(
            dimension=DimensionName.SEMANTIC_FIT,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EVALUATED,
            raw_value=Decimal("80"),
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
            rationale="Invalid mixed evaluation state.",
        )


def test_excluded_dimension_cannot_have_raw_value() -> None:
    with pytest.raises(DimensionEvaluationError):
        evaluate_dimension(
            dimension=DimensionName.LINKEDIN_EVIDENCE,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EXCLUDED,
            raw_value=Decimal("0"),
            exclusion_reason=ExclusionReason.UNAVAILABLE,
            rationale="Excluded dimension must not contain a score.",
        )


def test_excluded_dimension_requires_exclusion_reason() -> None:
    with pytest.raises(DimensionEvaluationError):
        evaluate_dimension(
            dimension=DimensionName.LINKEDIN_EVIDENCE,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EXCLUDED,
            rationale="Missing exclusion reason.",
        )


def test_blank_rationale_is_rejected() -> None:
    with pytest.raises(DimensionEvaluationError):
        evaluate_dimension(
            dimension=DimensionName.SEMANTIC_FIT,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EVALUATED,
            raw_value=Decimal("80"),
            rationale="   ",
        )


def test_duplicate_evidence_refs_are_rejected() -> None:
    with pytest.raises(DimensionEvaluationError):
        evaluate_dimension(
            dimension=DimensionName.SEMANTIC_FIT,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EVALUATED,
            raw_value=Decimal("80"),
            evidence_refs=("evidence-1", "evidence-1"),
            rationale="Duplicate evidence reference.",
        )


def test_duplicate_dimensions_are_rejected() -> None:
    first = evaluate_dimension(
        dimension=DimensionName.SEMANTIC_FIT,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("80"),
        rationale="First semantic evaluation.",
    )

    second = evaluate_dimension(
        dimension=DimensionName.SEMANTIC_FIT,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("90"),
        rationale="Conflicting semantic evaluation.",
    )

    with pytest.raises(DimensionEvaluationError):
        assemble_evaluation_result(
            screening_id="screening-1",
            dimensions=(first, second),
        )


def test_dimension_order_is_deterministic() -> None:
    semantic = evaluate_dimension(
        dimension=DimensionName.SEMANTIC_FIT,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("80"),
        rationale="Semantic evaluation.",
    )

    must_have = evaluate_dimension(
        dimension=DimensionName.MUST_HAVE_COVERAGE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("90"),
        rationale="Must-have evaluation.",
    )

    seniority = evaluate_dimension(
        dimension=DimensionName.SENIORITY_SCOPE_ALIGNMENT,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("75"),
        rationale="Seniority evaluation.",
    )

    result = assemble_evaluation_result(
        screening_id="screening-1",
        dimensions=(semantic, seniority, must_have),
    )

    assert tuple(
        dimension.dimension
        for dimension in result.dimensions
    ) == (
        DimensionName.MUST_HAVE_COVERAGE,
        DimensionName.SEMANTIC_FIT,
        DimensionName.SENIORITY_SCOPE_ALIGNMENT,
    )


def test_assembly_does_not_recalculate_raw_values() -> None:
    first = evaluate_dimension(
        dimension=DimensionName.MUST_HAVE_COVERAGE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("61.23"),
        rationale="Existing deterministic value.",
    )

    second = evaluate_dimension(
        dimension=DimensionName.JD_ALIGNED_EXPERIENCE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("91.77"),
        rationale="Existing deterministic value.",
    )

    result = assemble_evaluation_result(
        screening_id="screening-1",
        dimensions=(first, second),
    )

    values = {
        evaluation.dimension: evaluation.raw_value
        for evaluation in result.dimensions
    }

    assert values[DimensionName.MUST_HAVE_COVERAGE] == Decimal("61.23")
    assert values[DimensionName.JD_ALIGNED_EXPERIENCE] == Decimal("91.77")


def test_excluded_dimension_is_not_converted_to_zero() -> None:
    evaluation = evaluate_dimension(
        dimension=DimensionName.PORTFOLIO_EVIDENCE,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EXCLUDED,
        exclusion_reason=ExclusionReason.NOT_FOUND,
        rationale="Portfolio evidence was not found.",
    )

    assert evaluation.raw_value is None
    assert evaluation.exclusion_reason is ExclusionReason.NOT_FOUND


def test_contradiction_refs_are_preserved_without_score_mutation() -> None:
    evaluation = evaluate_dimension(
        dimension=DimensionName.SENIORITY_SCOPE_ALIGNMENT,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("75"),
        provenance_refs=("provenance-1",),
        rationale="Deterministic seniority alignment.",
    )

    result = assemble_evaluation_result(
        screening_id="screening-1",
        dimensions=(evaluation,),
        contradiction_refs=("contradiction-1",),
    )

    assert result.contradiction_refs == ("contradiction-1",)
    assert result.dimensions[0].raw_value == Decimal("75")
    assert result.deterministic is True


def test_duplicate_contradiction_refs_are_rejected() -> None:
    evaluation = evaluate_dimension(
        dimension=DimensionName.SEMANTIC_FIT,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("80"),
        rationale="Semantic evaluation.",
    )

    with pytest.raises(DimensionEvaluationError):
        assemble_evaluation_result(
            screening_id="screening-1",
            dimensions=(evaluation,),
            contradiction_refs=(
                "contradiction-1",
                "contradiction-1",
            ),
        )


def test_blank_screening_id_is_rejected() -> None:
    evaluation = evaluate_dimension(
        dimension=DimensionName.SEMANTIC_FIT,
        applicability=ApplicabilityStatus.APPLICABLE,
        resolution=DimensionResolution.EVALUATED,
        raw_value=Decimal("80"),
        rationale="Semantic evaluation.",
    )

    with pytest.raises(DimensionEvaluationError):
        assemble_evaluation_result(
            screening_id="   ",
            dimensions=(evaluation,),
        )


def test_blank_references_are_rejected() -> None:
    with pytest.raises(DimensionEvaluationError):
        evaluate_dimension(
            dimension=DimensionName.SEMANTIC_FIT,
            applicability=ApplicabilityStatus.APPLICABLE,
            resolution=DimensionResolution.EVALUATED,
            raw_value=Decimal("80"),
            provenance_refs=("   ",),
            rationale="Invalid provenance reference.",
        )