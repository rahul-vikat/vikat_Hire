from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    AccessStatus,
    DerivationMethod,
    EvidenceStatus,
    Provenance,
    SourceType,
    MatchStatus,
    RequirementCategory,
    RequirementImportance,
    DimensionName,
    DimensionResolution,
    ExclusionReason,
)
from vikat_hire.contracts.evidence import Claim
from vikat_hire.contracts.matching import KeywordMatch
from vikat_hire.contracts.normalization import JDRequirement
from vikat_hire.evaluation.github_match import (
    GitHubEvaluationError,
    evaluate_github_evidence,
)


def _github_provenance() -> Provenance:
    return Provenance(
        provenance_id="github-provenance",
        source_type=SourceType.GITHUB,
        source_ref="github-source",
        method=DerivationMethod.API,
        access_status=AccessStatus.AUTHORIZED,
    )


def _resume_provenance() -> Provenance:
    return Provenance(
        provenance_id="resume-provenance",
        source_type=SourceType.RESUME_FILE,
        source_ref="resume-source",
        method=DerivationMethod.PARSER,
        access_status=AccessStatus.AUTHORIZED,
    )


def _requirement(
    requirement_id: str,
    text: str,
) -> JDRequirement:
    return JDRequirement(
        requirement_id=requirement_id,
        category=RequirementCategory.SKILL,
        importance=RequirementImportance.MUST_HAVE,
        text=text,
        source_type=SourceType.JD_FILE,
        source_ref="jd-source",
        evidence_refs=("jd-evidence",),
        provenance_refs=("jd-provenance",),
    )


def _claim(
    claim_id: str,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        subject="github",
        predicate="demonstrates",
        value="Python",
        provenance_refs=("github-provenance",),
    )


def _match(
    *,
    match_id: str,
    requirement_id: str,
    claim_id: str | None,
    status: MatchStatus,
    score: str,
) -> KeywordMatch:
    return KeywordMatch(
        match_id=match_id,
        requirement_id=requirement_id,
        candidate_claim_id=claim_id,
        match_type="github_requirement_match",
        status=status,
        score=Decimal(score),
        provenance_refs=("github-provenance",),
    )


def test_github_score_averages_evaluated_jd_requirements() -> None:
    requirements = (
        _requirement("req-python", "Python"),
        _requirement("req-fastapi", "FastAPI"),
        _requirement("req-docker", "Docker"),
        _requirement("req-kubernetes", "Kubernetes"),
    )

    claims = (
        _claim("claim-python"),
        _claim("claim-fastapi"),
        _claim("claim-docker"),
    )

    matches = (
        _match(
            match_id="match-python",
            requirement_id="req-python",
            claim_id="claim-python",
            status=MatchStatus.MATCHED,
            score="100",
        ),
        _match(
            match_id="match-fastapi",
            requirement_id="req-fastapi",
            claim_id="claim-fastapi",
            status=MatchStatus.PARTIAL,
            score="70",
        ),
        _match(
            match_id="match-docker",
            requirement_id="req-docker",
            claim_id="claim-docker",
            status=MatchStatus.NOT_MATCHED,
            score="0",
        ),
    )

    result = evaluate_github_evidence(
        requirements=requirements,
        claims=claims,
        matches=matches,
        provenances=(
            _github_provenance(),
        ),
    )

    assert result.dimension is DimensionName.GITHUB_EVIDENCE
    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("56.67")
    assert result.exclusion_reason is None
    assert result.requirement_refs == (
        "req-docker",
        "req-fastapi",
        "req-python",
    )


def test_unresolved_requirements_are_excluded() -> None:
    requirements = (
        _requirement("req-python", "Python"),
        _requirement("req-kubernetes", "Kubernetes"),
    )

    claims = (
        _claim("claim-python"),
    )

    matches = (
        _match(
            match_id="match-python",
            requirement_id="req-python",
            claim_id="claim-python",
            status=MatchStatus.MATCHED,
            score="100",
        ),
    )

    result = evaluate_github_evidence(
        requirements=requirements,
        claims=claims,
        matches=matches,
        provenances=(
            _github_provenance(),
        ),
    )

    assert result.resolution is DimensionResolution.EVALUATED
    assert result.raw_value == Decimal("100.00")
    assert result.requirement_refs == ("req-python",)


def test_no_evaluable_github_requirement_excludes_dimension() -> None:
    requirements = (
        _requirement("req-python", "Python"),
    )

    result = evaluate_github_evidence(
        requirements=requirements,
        claims=(),
        matches=(),
        provenances=(
            _github_provenance(),
        ),
    )

    assert result.dimension is DimensionName.GITHUB_EVIDENCE
    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.raw_value is None
    assert result.exclusion_reason is ExclusionReason.INSUFFICIENT_EVIDENCE


def test_missing_github_provenance_excludes_dimension_as_not_found() -> None:
    requirements = (
        _requirement("req-python", "Python"),
    )

    result = evaluate_github_evidence(
        requirements=requirements,
        claims=(),
        matches=(),
        provenances=(
            _resume_provenance(),
        ),
    )

    assert result.resolution is DimensionResolution.EXCLUDED
    assert result.exclusion_reason is ExclusionReason.NOT_FOUND


def test_unknown_claim_reference_is_rejected() -> None:
    requirements = (
        _requirement("req-python", "Python"),
    )

    matches = (
        _match(
            match_id="match-python",
            requirement_id="req-python",
            claim_id="missing-claim",
            status=MatchStatus.MATCHED,
            score="100",
        ),
    )

    with pytest.raises(
        GitHubEvaluationError,
        match="unknown candidate claim",
    ):
        evaluate_github_evidence(
            requirements=requirements,
            claims=(),
            matches=matches,
            provenances=(
                _github_provenance(),
            ),
        )


def test_unknown_requirement_reference_is_rejected() -> None:
    matches = (
        _match(
            match_id="match-python",
            requirement_id="missing-requirement",
            claim_id=None,
            status=MatchStatus.MATCHED,
            score="100",
        ),
    )

    with pytest.raises(
        GitHubEvaluationError,
        match="unknown JD requirement",
    ):
        evaluate_github_evidence(
            requirements=(),
            claims=(),
            matches=matches,
            provenances=(
                _github_provenance(),
            ),
        )