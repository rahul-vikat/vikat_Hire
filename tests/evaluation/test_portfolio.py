from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    AccessStatus,
    DerivationMethod,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
    MatchStatus,
    Provenance,
    RequirementCategory,
    RequirementImportance,
    SourceType,
)
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.matching import KeywordMatch
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.evaluation.portfolio import (
    PortfolioEvaluationError,
    evaluate_portfolio_evidence,
)


def _requirements() -> tuple[JDRequirement, ...]:
    return tuple(
        JDRequirement(
            requirement_id=name,
            text=name,
            category=RequirementCategory.SKILL,
            importance=RequirementImportance.MUST_HAVE,
            source_type=SourceType.JD_FILE,
            source_ref="jd-1",
            evidence_refs=("jd-evidence",),
            provenance_refs=("jd-prov",),
        )
        for name in (
            "Python",
            "FastAPI",
            "Docker",
            "Kubernetes",
        )
    )


def _provenance() -> Provenance:
    return Provenance(
        provenance_id="portfolio-prov",
        source_type=SourceType.PORTFOLIO,
        source_ref="portfolio-source",
        method=DerivationMethod.CRAWLER,
        access_status=AccessStatus.AUTHORIZED,
    )


def _claims() -> tuple[Claim, ...]:
    return tuple(
        Claim(
            claim_id=f"claim-{name}",
            subject="portfolio",
            predicate="demonstrates",
            value=name,
            provenance_refs=("portfolio-prov",),
        )
        for name in (
            "Python",
            "FastAPI",
            "Docker",
        )
    )


def _matches() -> tuple[KeywordMatch, ...]:
    requirements = _requirements()
    claims = _claims()

    return tuple(
        KeywordMatch(
            match_id=f"match-{requirement.requirement_id}",
            requirement_id=requirement.requirement_id,
            candidate_claim_id=claim.claim_id,
            match_type="portfolio_requirement_match",
            status=status,
            score=Decimal(score),
            provenance_refs=("portfolio-prov",),
        )
        for requirement, claim, status, score in zip(
            requirements,
            claims,
            (
                MatchStatus.MATCHED,
                MatchStatus.PARTIAL,
                MatchStatus.NOT_MATCHED,
            ),
            (
                "100",
                "70",
                "0",
            ),
        )
    )


def test_portfolio_score_averages_evaluable_requirements():
    result = evaluate_portfolio_evidence(
        requirements=_requirements(),
        claims=_claims(),
        matches=_matches(),
        provenances=(_provenance(),),
    )

    assert result.dimension is DimensionName.PORTFOLIO_EVIDENCE
    assert result.applicability.value == "applicable"
    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("56.67")
    assert result.requirement_refs == (
        "Docker",
        "FastAPI",
        "Python",
    )
    assert result.provenance_refs == ("portfolio-prov",)


def test_unresolved_requirements_are_excluded_from_denominator():
    requirements = _requirements()
    matches = _matches()

    result = evaluate_portfolio_evidence(
        requirements=requirements,
        claims=_claims(),
        matches=matches,
        provenances=(_provenance(),),
    )

    assert result.raw_value == Decimal("56.67")
    assert "Kubernetes" not in result.requirement_refs


def test_no_evaluable_requirements_are_excluded():
    result = evaluate_portfolio_evidence(
        requirements=_requirements(),
        claims=(),
        matches=(),
        provenances=(_provenance(),),
    )

    assert result.dimension is DimensionName.PORTFOLIO_EVIDENCE
    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.exclusion_reason is ExclusionReason.INSUFFICIENT_EVIDENCE


def test_missing_portfolio_provenance_is_not_found():
    result = evaluate_portfolio_evidence(
        requirements=_requirements(),
        claims=(),
        matches=(),
        provenances=(),
    )

    assert result.dimension is DimensionName.PORTFOLIO_EVIDENCE
    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.exclusion_reason is ExclusionReason.NOT_FOUND


def test_unknown_candidate_claim_reference_is_rejected():
    matches = (
        KeywordMatch(
            match_id="match-1",
            requirement_id="Python",
            candidate_claim_id="missing-claim",
            match_type="portfolio_requirement_match",
            status=MatchStatus.MATCHED,
            score=Decimal("100"),
            provenance_refs=("portfolio-prov",),
        ),
    )

    with pytest.raises(
        PortfolioEvaluationError,
        match="unknown candidate claim",
    ):
        evaluate_portfolio_evidence(
            requirements=_requirements(),
            claims=_claims(),
            matches=matches,
            provenances=(_provenance(),),
        )


def test_unknown_requirement_reference_is_rejected():
    matches = (
        KeywordMatch(
            match_id="match-1",
            requirement_id="missing-requirement",
            candidate_claim_id="claim-Python",
            match_type="portfolio_requirement_match",
            status=MatchStatus.MATCHED,
            score=Decimal("100"),
            provenance_refs=("portfolio-prov",),
        ),
    )

    with pytest.raises(
        PortfolioEvaluationError,
        match="unknown JD requirement",
    ):
        evaluate_portfolio_evidence(
            requirements=_requirements(),
            claims=_claims(),
            matches=matches,
            provenances=(_provenance(),),
        )


def test_non_portfolio_matches_are_ignored():
    linkedin_provenance = Provenance(
        provenance_id="linkedin-prov",
        source_type=SourceType.LINKEDIN,
        source_ref="linkedin-source",
        method=DerivationMethod.API,
        access_status=AccessStatus.AUTHORIZED,
    )

    claim = Claim(
        claim_id="linkedin-claim",
        subject="linkedin",
        predicate="demonstrates",
        value="Python",
        provenance_refs=("linkedin-prov",),
    )

    match = KeywordMatch(
        match_id="linkedin-match",
        requirement_id="Python",
        candidate_claim_id="linkedin-claim",
        match_type="linkedin_requirement_match",
        status=MatchStatus.MATCHED,
        score=Decimal("100"),
        provenance_refs=("linkedin-prov",),
    )

    result = evaluate_portfolio_evidence(
        requirements=_requirements(),
        claims=(claim,),
        matches=(match,),
        provenances=(linkedin_provenance, _provenance()),
    )

    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.exclusion_reason is ExclusionReason.INSUFFICIENT_EVIDENCE


def test_strongest_match_is_selected_deterministically():
    matches = (
        KeywordMatch(
            match_id="match-python-weak",
            requirement_id="Python",
            candidate_claim_id="claim-Python",
            match_type="portfolio_requirement_match",
            status=MatchStatus.PARTIAL,
            score=Decimal("70"),
            provenance_refs=("portfolio-prov",),
        ),
        KeywordMatch(
            match_id="match-python-strong",
            requirement_id="Python",
            candidate_claim_id="claim-Python",
            match_type="portfolio_requirement_match",
            status=MatchStatus.MATCHED,
            score=Decimal("100"),
            provenance_refs=("portfolio-prov",),
        ),
    )

    result = evaluate_portfolio_evidence(
        requirements=_requirements(),
        claims=_claims(),
        matches=matches,
        provenances=(_provenance(),),
    )

    assert result.raw_value == Decimal("100")


def test_duplicate_requirement_ids_are_rejected():
    requirements = _requirements()

    with pytest.raises(
        PortfolioEvaluationError,
        match="duplicate JD requirement IDs",
    ):
        evaluate_portfolio_evidence(
            requirements=(*requirements, requirements[0]),
            claims=_claims(),
            matches=_matches(),
            provenances=(_provenance(),),
        )


def test_duplicate_claim_ids_are_rejected():
    claims = _claims()

    with pytest.raises(
        PortfolioEvaluationError,
        match="duplicate candidate claim IDs",
    ):
        evaluate_portfolio_evidence(
            requirements=_requirements(),
            claims=(*claims, claims[0]),
            matches=_matches(),
            provenances=(_provenance(),),
        )


def test_duplicate_match_ids_are_rejected():
    matches = _matches()

    with pytest.raises(
        PortfolioEvaluationError,
        match="duplicate keyword match IDs",
    ):
        evaluate_portfolio_evidence(
            requirements=_requirements(),
            claims=_claims(),
            matches=(*matches, matches[0]),
            provenances=(_provenance(),),
        )


def test_duplicate_provenance_ids_are_rejected():
    provenance = _provenance()

    with pytest.raises(
        PortfolioEvaluationError,
        match="duplicate provenance IDs",
    ):
        evaluate_portfolio_evidence(
            requirements=_requirements(),
            claims=_claims(),
            matches=_matches(),
            provenances=(provenance, provenance),
        )