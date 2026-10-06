from decimal import Decimal

import pytest
from pydantic import ValidationError

from vikat_hire.config import (
    SCORING_CONFIGURATION_2_2_0,
    SCORING_RELEASE_2_2_0,
)
from vikat_hire.contracts.common import DimensionName


EXPECTED_WEIGHTS = {
    DimensionName.MUST_HAVE_COVERAGE: Decimal("30"),
    DimensionName.JD_ALIGNED_EXPERIENCE: Decimal("20"),
    DimensionName.SEMANTIC_FIT: Decimal("18"),
    DimensionName.SENIORITY_SCOPE_ALIGNMENT: Decimal("10"),
    DimensionName.NICE_TO_HAVE_COVERAGE: Decimal("7"),
    DimensionName.LINKEDIN_EVIDENCE: Decimal("5"),
    DimensionName.GITHUB_EVIDENCE: Decimal("5"),
    DimensionName.PORTFOLIO_EVIDENCE: Decimal("5"),
}


def test_authoritative_release_identifier() -> None:
    assert (
        SCORING_RELEASE_2_2_0.release
        == "verifyhire-scoring@2.2.0"
    )


def test_authoritative_weights_are_exact() -> None:
    assert dict(SCORING_CONFIGURATION_2_2_0.weights) == EXPECTED_WEIGHTS


def test_weights_sum_to_exactly_100() -> None:
    assert SCORING_CONFIGURATION_2_2_0.total_weight == Decimal("100")


def test_all_authoritative_dimensions_are_present() -> None:
    assert set(SCORING_CONFIGURATION_2_2_0.weights) == set(DimensionName)


def test_weights_are_decimal() -> None:
    assert all(
        isinstance(weight, Decimal)
        for weight in SCORING_CONFIGURATION_2_2_0.weights.values()
    )


def test_configuration_is_immutable() -> None:
    with pytest.raises(TypeError):
        SCORING_CONFIGURATION_2_2_0.weights[
            DimensionName.MUST_HAVE_COVERAGE
        ] = Decimal("99")


def test_configuration_field_is_frozen() -> None:
    with pytest.raises(ValidationError):
        SCORING_CONFIGURATION_2_2_0.release = SCORING_RELEASE_2_2_0


def test_weight_lookup_returns_exact_decimal() -> None:
    assert (
        SCORING_CONFIGURATION_2_2_0.weight_for(
            DimensionName.MUST_HAVE_COVERAGE
        )
        == Decimal("30")
    )


def test_negative_weight_is_rejected() -> None:
    weights = dict(EXPECTED_WEIGHTS)
    weights[DimensionName.MUST_HAVE_COVERAGE] = Decimal("-1")

    with pytest.raises(ValidationError, match="must not be negative"):
        type(SCORING_CONFIGURATION_2_2_0)(
            release=SCORING_RELEASE_2_2_0,
            weights=weights,
        )


def test_wrong_total_is_rejected() -> None:
    weights = dict(EXPECTED_WEIGHTS)
    weights[DimensionName.MUST_HAVE_COVERAGE] = Decimal("29")

    with pytest.raises(ValidationError, match="sum to exactly 100"):
        type(SCORING_CONFIGURATION_2_2_0)(
            release=SCORING_RELEASE_2_2_0,
            weights=weights,
        )


def test_missing_dimension_is_rejected() -> None:
    weights = dict(EXPECTED_WEIGHTS)
    del weights[DimensionName.PORTFOLIO_EVIDENCE]

    with pytest.raises(ValidationError, match="missing dimensions"):
        type(SCORING_CONFIGURATION_2_2_0)(
            release=SCORING_RELEASE_2_2_0,
            weights=weights,
        )


def test_unknown_dimension_is_rejected() -> None:
    # Pydantic will reject an enum key that is not part of DimensionName.
    weights = dict(EXPECTED_WEIGHTS)
    weights["unknown_dimension"] = Decimal("0")  # type: ignore[index]

    with pytest.raises(ValidationError):
        type(SCORING_CONFIGURATION_2_2_0)(
            release=SCORING_RELEASE_2_2_0,
            weights=weights,
        )


def test_configuration_serializes_without_mutability_leak() -> None:
    dumped = SCORING_CONFIGURATION_2_2_0.model_dump()

    assert dumped["release"]["release"] == "verifyhire-scoring@2.2.0"
    assert (
        dumped["weights"][DimensionName.MUST_HAVE_COVERAGE]
        == Decimal("30")
    )

    dumped["weights"][DimensionName.MUST_HAVE_COVERAGE] = Decimal("99")

    assert (
        SCORING_CONFIGURATION_2_2_0.weight_for(
            DimensionName.MUST_HAVE_COVERAGE
        )
        == Decimal("30")
    )