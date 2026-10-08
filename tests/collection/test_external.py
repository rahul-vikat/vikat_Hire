from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vikat_hire.collection.external import (
    ExternalCollectionError,
    ExternalCollectionResult,
)
from vikat_hire.contracts.collection import (
    CollectedSource,
    CollectionStatus,
)
from vikat_hire.contracts.common import (
    AccessStatus,
    DerivationMethod,
    Provenance,
    SourceType,
)
from vikat_hire.contracts.inputs import ExternalSourceInput
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    ExtractionKind,
)


def _provenance() -> Provenance:
    return Provenance(
        provenance_id="prov-1",
        source_type=SourceType.GITHUB,
        source_ref="github-source-1",
        source_uri="https://github.com/example",
        retrieved_at=datetime.now(UTC),
        observed_at=datetime.now(UTC),
        method=DerivationMethod.API,
        access_status=AccessStatus.AUTHORIZED,
    )


def _source(
    *,
    provenance_refs: tuple[str, ...] = ("prov-1",),
) -> CollectedSource:
    return CollectedSource(
        source_type=SourceType.GITHUB,
        source_ref="github-source-1",
        source_uri="https://github.com/example",
        access_status=AccessStatus.AUTHORIZED,
        status=CollectionStatus.COLLECTED,
        provenance_refs=provenance_refs,
    )


def _block(
    *,
    block_id: str = "block-1",
    provenance_refs: tuple[str, ...] = ("prov-1",),
) -> ExtractedTextBlock:
    return ExtractedTextBlock(
        block_id=block_id,
        source_type=SourceType.GITHUB,
        source_ref="github-source-1",
        text="Python FastAPI PostgreSQL",
        extraction_kind=ExtractionKind.PLAIN_TEXT,
        provenance_refs=provenance_refs,
    )


def _source_input() -> ExternalSourceInput:
    return ExternalSourceInput(
        github_url="https://github.com/example",
    )


def test_external_collection_result_accepts_valid_collected_source() -> None:
    result = ExternalCollectionResult(
        source=_source(),
        provenances=(_provenance(),),
        extracted_blocks=(_block(),),
    )

    assert result.source.source_type is SourceType.GITHUB
    assert result.provenances[0].provenance_id == "prov-1"
    assert result.extracted_blocks[0].block_id == "block-1"


def test_external_collection_result_rejects_unknown_source_provenance() -> None:
    with pytest.raises(
        ExternalCollectionError,
        match="source contains unknown provenance references",
    ):
        ExternalCollectionResult(
            source=_source(provenance_refs=("unknown",)),
            provenances=(_provenance(),),
            extracted_blocks=(_block(),),
        )


def test_external_collection_result_rejects_duplicate_block_ids() -> None:
    with pytest.raises(
        ExternalCollectionError,
        match="duplicate extracted block id",
    ):
        ExternalCollectionResult(
            source=_source(),
            provenances=(_provenance(),),
            extracted_blocks=(
                _block(block_id="duplicate"),
                _block(block_id="duplicate"),
            ),
        )


def test_external_collection_result_rejects_wrong_block_source_type() -> None:
    block = _block().model_copy(
        update={
            "source_type": SourceType.LINKEDIN,
        }
    )

    with pytest.raises(
        ExternalCollectionError,
        match="source type does not match",
    ):
        ExternalCollectionResult(
            source=_source(),
            provenances=(_provenance(),),
            extracted_blocks=(block,),
        )


def test_external_collection_result_rejects_wrong_block_source_ref() -> None:
    block = _block().model_copy(
        update={
            "source_ref": "different-source",
        }
    )

    with pytest.raises(
        ExternalCollectionError,
        match="source reference does not match",
    ):
        ExternalCollectionResult(
            source=_source(),
            provenances=(_provenance(),),
            extracted_blocks=(block,),
        )


def test_external_collection_result_rejects_unknown_block_provenance() -> None:
    block = _block(provenance_refs=("unknown",))

    with pytest.raises(
        ExternalCollectionError,
        match="extracted block contains unknown provenance",
    ):
        ExternalCollectionResult(
            source=_source(),
            provenances=(_provenance(),),
            extracted_blocks=(block,),
        )


def test_external_collection_result_rejects_collected_source_without_blocks() -> None:
    with pytest.raises(
        ExternalCollectionError,
        match="must contain extracted blocks",
    ):
        ExternalCollectionResult(
            source=_source(),
            provenances=(_provenance(),),
            extracted_blocks=(),
        )


def test_external_collection_result_allows_non_applicable_source_without_blocks() -> None:
    source = CollectedSource(
        source_type=SourceType.GITHUB,
        source_ref="github-source-1",
        source_uri=None,
        access_status=None,
        status=CollectionStatus.NOT_APPLICABLE,
        provenance_refs=(),
    )

    result = ExternalCollectionResult(
        source=source,
        provenances=(),
        extracted_blocks=(),
    )

    assert result.extracted_blocks == ()
    assert result.provenances == ()


def test_external_source_input_remains_provider_neutral() -> None:
    source_input = _source_input()

    assert source_input.github_url is not None
    assert source_input.github_authorized is True
