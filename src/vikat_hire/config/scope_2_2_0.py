from __future__ import annotations

# from .models import ImmutableScoringConfiguration  # noqa: F401
from ..contracts.common import ScopeLevel
from ..contracts.scope import (
    ScopeEvidenceCategory,
    ScopeGate,
    ScopeTaxonomyConfiguration,
)


SCOPE_TAXONOMY_VERSION_2_2_0 = "2.2.0"


SCOPE_TAXONOMY_2_2_0 = ScopeTaxonomyConfiguration(
    taxonomy_version=SCOPE_TAXONOMY_VERSION_2_2_0,
    gates=(
        ScopeGate(
            level=ScopeLevel.L0,
            required_categories=(),
            supporting_categories=(),
            requires_supervision_learning=True,
            rationale=(
                "L0 requires explicit supervised or learning scope evidence. "
                "Absence of independent ownership is not itself treated as "
                "positive evidence."
            ),
        ),
        ScopeGate(
            level=ScopeLevel.L1,
            required_categories=(
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            supporting_categories=(
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
            rationale=(
                "L1 requires explicit evidence that the candidate independently "
                "executes assigned work within an established system."
            ),
        ),
        ScopeGate(
            level=ScopeLevel.L2,
            required_categories=(
                ScopeEvidenceCategory.OWNERSHIP,
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
            supporting_categories=(
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
            rationale=(
                "L2 requires end-to-end ownership together with local technical "
                "decision authority."
            ),
        ),
        ScopeGate(
            level=ScopeLevel.L3,
            required_categories=(
                ScopeEvidenceCategory.OWNERSHIP,
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
                ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP,
            ),
            supporting_categories=(
                ScopeEvidenceCategory.ARCHITECTURE,
                ScopeEvidenceCategory.PEOPLE_LEADERSHIP,
            ),
            rationale=(
                "L3 requires complex ownership, significant technical decision "
                "authority, and production responsibility."
            ),
        ),
        ScopeGate(
            level=ScopeLevel.L4,
            required_categories=(
                ScopeEvidenceCategory.CROSS_TEAM_SCOPE,
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
            ),
            supporting_categories=(
                ScopeEvidenceCategory.ARCHITECTURE,
                ScopeEvidenceCategory.PEOPLE_LEADERSHIP,
                ScopeEvidenceCategory.OWNERSHIP,
            ),
            rationale=(
                "L4 requires broad cross-team scope and technical decision "
                "authority. Architecture, ownership, and people leadership "
                "strengthen the evidence but cannot substitute for the gate."
            ),
        ),
        ScopeGate(
            level=ScopeLevel.L5,
            required_categories=(
                ScopeEvidenceCategory.ENGINEERING_STRATEGY,
                ScopeEvidenceCategory.ARCHITECTURE,
            ),
            supporting_categories=(
                ScopeEvidenceCategory.CROSS_TEAM_SCOPE,
                ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY,
                ScopeEvidenceCategory.PEOPLE_LEADERSHIP,
            ),
            rationale=(
                "L5 requires organization-level engineering strategy and "
                "architecture-direction evidence."
            ),
        ),
    ),
)


def get_scope_taxonomy_2_2_0() -> ScopeTaxonomyConfiguration:
    return SCOPE_TAXONOMY_2_2_0