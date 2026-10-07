from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.contracts.common import (
    RequirementCategory,
    RequirementImportance,
    ScopeEvidenceCategory,
)
from vikat_hire.contracts.normalization import ExtractedTextBlock
from vikat_hire.contracts.scope import ScopeEvidencePolarity
from vikat_hire.normalization.jd import normalize_jd


def _block(
    block_id: str,
    text: str,
    *,
    provenance_refs: tuple[str, ...] = ("resume-source",),
) -> ExtractedTextBlock:
    return ExtractedTextBlock(
        block_id=block_id,
        source_type="jd_file",
        source_ref="jd-1",
        text=text,
        provenance_refs=provenance_refs,
    )


def test_empty_jd_produces_empty_normalization() -> None:
    requirements, experience, scope = normalize_jd(
        blocks=(),
        screening_id="screening-1",
    )

    assert requirements == ()
    assert experience == ()
    assert scope == ()


def test_must_have_requirement_is_normalized_without_evaluation() -> None:
    requirements, experience, scope = normalize_jd(
        blocks=(
            _block(
                "block-1",
                "Must have: Python and PostgreSQL",
            ),
        ),
        screening_id="screening-1",
    )

    assert len(requirements) == 1

    result = requirements[0]

    assert result.category is RequirementCategory.MUST_HAVE
    assert result.importance is RequirementImportance.MUST_HAVE
    assert result.text == "Python and PostgreSQL"
    assert result.provenance_refs == ("resume-source",)
    assert not hasattr(result, "score")
    assert not hasattr(result, "match")


def test_nice_to_have_requirement_is_normalized() -> None:
    requirements, _, _ = normalize_jd(
        blocks=(
            _block(
                "block-1",
                "Nice to have: experience with AWS",
            ),
        ),
        screening_id="screening-1",
    )

    assert len(requirements) == 1
    assert requirements[0].category is RequirementCategory.NICE_TO_HAVE
    assert requirements[0].importance is RequirementImportance.NICE_TO_HAVE


def test_minimum_years_is_preserved_as_decimal() -> None:
    requirements, experience, _ = normalize_jd(
        blocks=(
            _block(
                "block-1",
                "Must have: at least 5 years of Python experience",
            ),
        ),
        screening_id="screening-1",
    )

    assert len(requirements) == 1
    assert len(experience) == 1

    result = experience[0]

    assert result.minimum_years == Decimal("5")
    assert result.requirement_id == requirements[0].requirement_id


def test_decimal_minimum_years_is_preserved() -> None:
    _, experience, _ = normalize_jd(
        blocks=(
            _block(
                "block-1",
                "Required: 3.5 years experience building APIs",
            ),
        ),
        screening_id="screening-1",
    )

    assert experience[0].minimum_years == Decimal("3.5")


def test_scope_evidence_is_supporting_and_not_classified() -> None:
    _, _, scope = normalize_jd(
        blocks=(
            _block(
                "block-1",
                "Own services end-to-end and make architecture decisions.",
            ),
        ),
        screening_id="screening-1",
    )

    assert len(scope) == 1

    result = scope[0]

    assert ScopeEvidenceCategory.OWNERSHIP in result.categories
    assert ScopeEvidenceCategory.ARCHITECTURE in result.categories
    assert (
        ScopeEvidenceCategory.TECHNICAL_DECISION_AUTHORITY
        in result.categories
    )
    assert result.polarity is ScopeEvidencePolarity.SUPPORTING
    assert result.explicit_text == (
        "Own services end-to-end and make architecture decisions."
    )

    assert not hasattr(result, "required_level")
    assert not hasattr(result, "score")


def test_supervision_is_explicit_jd_scope_evidence() -> None:
    _, _, scope = normalize_jd(
        blocks=(
            _block(
                "block-1",
                "This role works under direct supervision.",
            ),
        ),
        screening_id="screening-1",
    )

    assert len(scope) == 1
    assert scope[0].supervision_learning is True
    assert scope[0].categories == ()
    assert scope[0].polarity is ScopeEvidencePolarity.CONTRADICTING


def test_scope_polarity_is_preserved() -> None:
    _, _, scope = normalize_jd(
        blocks=(
            _block(
                "block-1",
                "No responsibility for production ownership.",
            ),
        ),
        screening_id="screening-1",
    )

    assert len(scope) == 1
    assert (
        ScopeEvidenceCategory.PRODUCTION_OPERATIONAL_OWNERSHIP
        in scope[0].categories
    )
    assert scope[0].polarity is ScopeEvidencePolarity.CONTRADICTING


def test_scope_does_not_assign_level() -> None:
    _, _, scope = normalize_jd(
        blocks=(
            _block(
                "block-1",
                "Lead architecture across multiple teams.",
            ),
        ),
        screening_id="screening-1",
    )

    assert len(scope) == 1
    assert not hasattr(scope[0], "level")
    assert not hasattr(scope[0], "required_level")


def test_provenance_is_preserved_per_source() -> None:
    _, _, scope = normalize_jd(
        blocks=(
            _block(
                "block-1",
                "Own production services.",
                provenance_refs=("jd-page-1",),
            ),
            _block(
                "block-2",
                "Own production services.",
                provenance_refs=("jd-page-3",),
            ),
        ),
        screening_id="screening-1",
    )

    assert len(scope) == 2
    assert scope[0].provenance_refs == ("jd-page-1",)
    assert scope[1].provenance_refs == ("jd-page-3",)


def test_duplicate_block_ids_fail() -> None:
    with pytest.raises(ValueError, match="duplicate extracted block IDs"):
        normalize_jd(
            blocks=(
                _block("same", "Must have: Python"),
                _block("same", "Must have: PostgreSQL"),
            ),
            screening_id="screening-1",
        )


def test_blank_screening_id_fails() -> None:
    with pytest.raises(ValueError, match="screening_id"):
        normalize_jd(
            blocks=(),
            screening_id=" ",
        )


def test_zero_minimum_years_fails() -> None:
    with pytest.raises(ValueError, match="minimum_years"):
        normalize_jd(
            blocks=(
                _block(
                    "block-1",
                    "Required: 0 years experience",
                ),
            ),
            screening_id="screening-1",
        )