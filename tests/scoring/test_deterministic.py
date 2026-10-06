from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.config.scoring_2_2_0 import SCORING_CONFIGURATION_2_2_0
from vikat_hire.contracts.common import ApplicabilityStatus, DimensionName, DimensionResolution, ExclusionReason
from vikat_hire.contracts.evaluation import DimensionEvaluation
from vikat_hire.scoring.deterministic import DeterministicScoringError, calculate_score


def _evaluation(dimension: DimensionName, raw_value: str | None, *, applicability: ApplicabilityStatus = ApplicabilityStatus.APPLICABLE, resolution: DimensionResolution = DimensionResolution.EVALUATED) -> DimensionEvaluation:
    return DimensionEvaluation(dimension=dimension, applicability=applicability, resolution=resolution, raw_value=Decimal(raw_value) if raw_value is not None else None, exclusion_reason=None if raw_value is not None else ExclusionReason.INSUFFICIENT_EVIDENCE, evidence_refs=(f"evidence-{dimension.value}",), provenance_refs=(f"provenance-{dimension.value}",), rationale=f"Evaluation for {dimension.value}.")


def test_calculate_score_uses_applicability_renormalization() -> None:
    evaluations = tuple(_evaluation(d, v) for d, v in ((DimensionName.MUST_HAVE_COVERAGE, "80"), (DimensionName.JD_ALIGNED_EXPERIENCE, "70"), (DimensionName.SEMANTIC_FIT, "90"), (DimensionName.SENIORITY_SCOPE_ALIGNMENT, "60"), (DimensionName.NICE_TO_HAVE_COVERAGE, "50"))) + tuple(_evaluation(d, None, resolution=DimensionResolution.EXCLUDED) for d in (DimensionName.LINKEDIN_EVIDENCE, DimensionName.GITHUB_EVIDENCE, DimensionName.PORTFOLIO_EVIDENCE))
    result = calculate_score(screening_id="screening-1", evaluations=evaluations, configuration=SCORING_CONFIGURATION_2_2_0)
    assert result.score == Decimal("76.13")
    assert result.applicable_weight_total == Decimal("80")


def test_missing_evidence_is_not_a_penalty() -> None:
    complete = tuple(_evaluation(d, "80") for d in (DimensionName.MUST_HAVE_COVERAGE, DimensionName.JD_ALIGNED_EXPERIENCE))
    with_missing = complete + (_evaluation(DimensionName.LINKEDIN_EVIDENCE, None, resolution=DimensionResolution.EXCLUDED),)
    assert calculate_score(screening_id="missing", evaluations=with_missing, configuration=SCORING_CONFIGURATION_2_2_0).score == calculate_score(screening_id="complete", evaluations=complete, configuration=SCORING_CONFIGURATION_2_2_0).score


def test_evaluated_zero_is_not_excluded() -> None:
    result = calculate_score(screening_id="screening-zero", evaluations=(_evaluation(DimensionName.MUST_HAVE_COVERAGE, "0"),), configuration=SCORING_CONFIGURATION_2_2_0)
    assert result.score == Decimal("0")
    assert result.applicable_weight_total == Decimal("30")
    assert result.dimensions[0].resolution is DimensionResolution.EVALUATED
    assert result.dimensions[0].raw_value == Decimal("0")
    assert result.dimensions[0].weighted_contribution == Decimal("0")


def test_all_excluded_dimensions_produce_no_score() -> None:
    result = calculate_score(screening_id="screening-none", evaluations=tuple(_evaluation(d, None, resolution=DimensionResolution.EXCLUDED) for d in DimensionName), configuration=SCORING_CONFIGURATION_2_2_0)
    assert result.score is None
    assert result.applicable_weight_total == Decimal("0")
    assert result.audit == ()


def test_duplicate_dimensions_are_rejected() -> None:
    with pytest.raises(DeterministicScoringError, match="duplicate dimension evaluation"):
        calculate_score(screening_id="screening-duplicate", evaluations=(_evaluation(DimensionName.MUST_HAVE_COVERAGE, "80"), _evaluation(DimensionName.MUST_HAVE_COVERAGE, "90")), configuration=SCORING_CONFIGURATION_2_2_0)


def test_excluded_dimension_cannot_have_raw_value() -> None:
    with pytest.raises(ValueError):
        calculate_score(screening_id="screening-invalid", evaluations=(_evaluation(DimensionName.MUST_HAVE_COVERAGE, "0", resolution=DimensionResolution.EXCLUDED),), configuration=SCORING_CONFIGURATION_2_2_0)


def test_scored_dimension_requires_raw_value() -> None:
    with pytest.raises(ValueError, match="evaluated dimension"):
        calculate_score(screening_id="screening-invalid", evaluations=(_evaluation(DimensionName.MUST_HAVE_COVERAGE, None, resolution=DimensionResolution.EVALUATED),), configuration=SCORING_CONFIGURATION_2_2_0)


def test_score_audit_preserves_configuration_and_evidence() -> None:
    evaluation = _evaluation(DimensionName.MUST_HAVE_COVERAGE, "80")
    result = calculate_score(screening_id="screening-audit", evaluations=(evaluation,), configuration=SCORING_CONFIGURATION_2_2_0)
    assert len(result.audit) == 1
    audit = result.audit[0]
    assert audit.dimension is DimensionName.MUST_HAVE_COVERAGE
    assert audit.input_evaluation_ref == evaluation.dimension_id
    assert audit.evidence_refs == evaluation.evidence_refs
    assert audit.configuration_ref == "verifyhire-scoring@2.2.0"
    assert audit.weight == Decimal("30")
    assert audit.normalized_value == Decimal("0.8")
    assert audit.weighted_contribution == Decimal("24")
