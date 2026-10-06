from decimal import Decimal

import pytest
from pydantic import ValidationError

from vikat_hire.contracts.common import (
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    ScopeLevel,
)
from vikat_hire.contracts.evaluation import SeniorityScopeEvaluation


def test_scope_levels_are_l0_through_l5() -> None:
    assert tuple(level.value for level in ScopeLevel) == (
        "L0",
        "L1",
        "L2",
        "L3",
        "L4",
        "L5",
    )


def test_evaluated_seniority_scope_contract() -> None:
    evaluation = SeniorityScopeEvaluation(
        candidate_level=ScopeLevel.L3,
        required_level=ScopeLevel.L2,
        resolution=DimensionResolution.EVALUATED,
        delta=1,
        raw_value=Decimal("90"),
        evidence_refs=("evidence-1",),
        provenance_refs=("provenance-1",),
        rationale="Candidate scope is one level above the required scope.",
    )

    assert evaluation.dimension == DimensionName.SENIORITY_SCOPE_ALIGNMENT
    assert evaluation.candidate_level == ScopeLevel.L3
    assert evaluation.required_level == ScopeLevel.L2
    assert evaluation.delta == 1
    assert evaluation.raw_value == Decimal("90")


def test_excluded_seniority_scope_contract() -> None:
    evaluation = SeniorityScopeEvaluation(
        candidate_level=None,
        required_level=ScopeLevel.L3,
        resolution=DimensionResolution.EXCLUDED,
        evidence_refs=(),
        provenance_refs=("jd-provenance-1",),
        exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
        rationale="Candidate scope could not be established from validated evidence.",
    )

    assert evaluation.resolution == DimensionResolution.EXCLUDED
    assert evaluation.raw_value is None
    assert evaluation.delta is None
    assert evaluation.exclusion_reason == ExclusionReason.INSUFFICIENT_EVIDENCE


def test_evaluated_scope_requires_candidate_level() -> None:
    with pytest.raises(ValidationError):
        SeniorityScopeEvaluation(
            candidate_level=None,
            required_level=ScopeLevel.L3,
            resolution=DimensionResolution.EVALUATED,
            delta=-1,
            raw_value=Decimal("75"),
            provenance_refs=("provenance-1",),
            rationale="Missing candidate scope.",
        )


def test_evaluated_scope_requires_required_level() -> None:
    with pytest.raises(ValidationError):
        SeniorityScopeEvaluation(
            candidate_level=ScopeLevel.L3,
            required_level=None,
            resolution=DimensionResolution.EVALUATED,
            delta=0,
            raw_value=Decimal("100"),
            provenance_refs=("provenance-1",),
            rationale="Missing required scope.",
        )


def test_evaluated_scope_requires_delta() -> None:
    with pytest.raises(ValidationError):
        SeniorityScopeEvaluation(
            candidate_level=ScopeLevel.L3,
            required_level=ScopeLevel.L3,
            resolution=DimensionResolution.EVALUATED,
            delta=None,
            raw_value=Decimal("100"),
            provenance_refs=("provenance-1",),
            rationale="Missing delta.",
        )


def test_evaluated_scope_requires_raw_value() -> None:
    with pytest.raises(ValidationError):
        SeniorityScopeEvaluation(
            candidate_level=ScopeLevel.L3,
            required_level=ScopeLevel.L3,
            resolution=DimensionResolution.EVALUATED,
            delta=0,
            raw_value=None,
            provenance_refs=("provenance-1",),
            rationale="Missing raw score.",
        )


def test_evaluated_scope_cannot_have_exclusion_reason() -> None:
    with pytest.raises(ValidationError):
        SeniorityScopeEvaluation(
            candidate_level=ScopeLevel.L3,
            required_level=ScopeLevel.L3,
            resolution=DimensionResolution.EVALUATED,
            delta=0,
            raw_value=Decimal("100"),
            provenance_refs=("provenance-1",),
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
            rationale="Invalid mixed state.",
        )


def test_excluded_scope_cannot_have_raw_value() -> None:
    with pytest.raises(ValidationError):
        SeniorityScopeEvaluation(
            candidate_level=None,
            required_level=ScopeLevel.L3,
            resolution=DimensionResolution.EXCLUDED,
            raw_value=Decimal("0"),
            provenance_refs=("provenance-1",),
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
            rationale="Excluded result cannot contain a score.",
        )


def test_excluded_scope_cannot_have_delta() -> None:
    with pytest.raises(ValidationError):
        SeniorityScopeEvaluation(
            candidate_level=None,
            required_level=ScopeLevel.L3,
            resolution=DimensionResolution.EXCLUDED,
            delta=-3,
            provenance_refs=("provenance-1",),
            exclusion_reason=ExclusionReason.INSUFFICIENT_EVIDENCE,
            rationale="Excluded result cannot contain a delta.",
        )


def test_excluded_scope_requires_exclusion_reason() -> None:
    with pytest.raises(ValidationError):
        SeniorityScopeEvaluation(
            candidate_level=None,
            required_level=ScopeLevel.L3,
            resolution=DimensionResolution.EXCLUDED,
            provenance_refs=("provenance-1",),
            rationale="Missing exclusion reason.",
        )


def test_delta_outside_l0_l5_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SeniorityScopeEvaluation(
            candidate_level=ScopeLevel.L5,
            required_level=ScopeLevel.L0,
            resolution=DimensionResolution.EVALUATED,
            delta=6,
            raw_value=Decimal("100"),
            provenance_refs=("provenance-1",),
            rationale="Invalid delta.",
        )


def test_rationale_cannot_be_blank() -> None:
    with pytest.raises(ValidationError):
        SeniorityScopeEvaluation(
            candidate_level=ScopeLevel.L3,
            required_level=ScopeLevel.L2,
            resolution=DimensionResolution.EVALUATED,
            delta=1,
            raw_value=Decimal("90"),
            provenance_refs=("provenance-1",),
            rationale="   ",
        )


def test_scope_contract_is_immutable() -> None:
    evaluation = SeniorityScopeEvaluation(
        candidate_level=ScopeLevel.L3,
        required_level=ScopeLevel.L2,
        resolution=DimensionResolution.EVALUATED,
        delta=1,
        raw_value=Decimal("90"),
        provenance_refs=("provenance-1",),
        rationale="Valid evaluation.",
    )

    with pytest.raises(ValidationError):
        evaluation.raw_value = Decimal("75")