from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    ApplicabilityStatus,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    ScopeLevel,
)
from vikat_hire.contracts.evaluation import SeniorityScopeEvaluation
from vikat_hire.evaluation.dimensions import (
    DimensionEvaluationError,
    evaluate_seniority_dimension,
)


def test_seniority_evaluation_is_converted_without_recalculation() -> None:
    seniority = SeniorityScopeEvaluation(
        candidate_level=ScopeLevel.L2,
        required_level=ScopeLevel.L3,
        resolution=DimensionResolution.EVALUATED,
        delta=-1,
        raw_value=Decimal("75"),
        evidence_refs=("candidate-scope-1",),
        provenance_refs=("resume-provenance", "jd-provenance"),
        rationale="Candidate scope L2 is one level below required L3.",
    )

    result = evaluate_seniority_dimension(
        evaluation=seniority,
    )

    assert result.dimension is DimensionName.SENIORITY_SCOPE_ALIGNMENT
    assert result.applicability is ApplicabilityStatus.APPLICABLE
    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("75")
    assert result.evidence_refs == ("candidate-scope-1",)
    assert result.provenance_refs == (
        "resume-provenance",
        "jd-provenance",
    )
    assert result.exclusion_reason is None


def test_excluded_seniority_is_preserved_without_zeroing() -> None:
    seniority = SeniorityScopeEvaluation(
        candidate_level=None,
        required_level=None,
        resolution=DimensionResolution.EXCLUDED,
        evidence_refs=(),
        provenance_refs=("resume-provenance", "jd-provenance"),
        exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
        rationale="Insufficient scope evidence.",
    )

    result = evaluate_seniority_dimension(
        evaluation=seniority,
    )

    assert result.dimension is DimensionName.SENIORITY_SCOPE_ALIGNMENT
    assert result.applicability is ApplicabilityStatus.APPLICABLE
    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.exclusion_reason is ExclusionReason.INSUFFICIENT_EVIDENCE


def test_seniority_dimension_rejects_wrong_dimension() -> None:
    seniority = SeniorityScopeEvaluation(
        candidate_level=ScopeLevel.L2,
        required_level=ScopeLevel.L2,
        resolution=DimensionResolution.EVALUATED,
        delta=0,
        raw_value=Decimal("100"),
        provenance_refs=("resume-provenance",),
        rationale="Candidate scope matches required scope.",
    )

    seniority = seniority.model_copy(
        update={
            "dimension": DimensionName.MUST_HAVE_COVERAGE,
        }
    )

    with pytest.raises(
        DimensionEvaluationError,
        match="SENIORITY_SCOPE_ALIGNMENT",
    ):
        evaluate_seniority_dimension(
            evaluation=seniority,
        )


def test_seniority_dimension_rejects_non_seniority_input() -> None:
    with pytest.raises(
        DimensionEvaluationError,
        match="SeniorityScopeEvaluation",
    ):
        evaluate_seniority_dimension(
            evaluation=object(),  # type: ignore[arg-type]
        )