from decimal import Decimal

import pytest

from vikat_hire.contracts import DimensionName, ScoringConfiguration


def test_authoritative_2_2_0_weights_sum_to_100() -> None:
    config = ScoringConfiguration(
        config_id="verifyhire-scoring@2.2.0",
        release="2.2.0",
        weights={
            DimensionName.MUST_HAVE_COVERAGE: Decimal("30"),
            DimensionName.JD_ALIGNED_EXPERIENCE: Decimal("20"),
            DimensionName.SEMANTIC_FIT: Decimal("18"),
            DimensionName.SENIORITY_SCOPE_ALIGNMENT: Decimal("10"),
            DimensionName.NICE_TO_HAVE_COVERAGE: Decimal("7"),
            DimensionName.LINKEDIN_EVIDENCE: Decimal("5"),
            DimensionName.GITHUB_EVIDENCE: Decimal("5"),
            DimensionName.PORTFOLIO_EVIDENCE: Decimal("5"),
        },
    )

    assert sum(config.weights.values(), Decimal("0")) == Decimal("100")


def test_scoring_configuration_rejects_wrong_total() -> None:
    with pytest.raises(ValueError, match="must sum to exactly 100"):
        ScoringConfiguration(
            config_id="invalid",
            release="invalid",
            weights={
                dimension: Decimal("10")
                for dimension in DimensionName
            },
        )