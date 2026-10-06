from decimal import Decimal

from vikat_hire.contracts.common import DimensionName

from .models import ImmutableScoringConfiguration, ScoringRelease


SCORING_RELEASE_2_2_0 = ScoringRelease(
    release="verifyhire-scoring@2.2.0",
    schema_version="vikat_hire.scoring.v1",
    description=(
        "Independent weighted-mean scoring with applicability "
        "renormalization and independently weighted external evidence."
    ),
)


SCORING_CONFIGURATION_2_2_0 = ImmutableScoringConfiguration(
    release=SCORING_RELEASE_2_2_0,
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