from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vikat_hire.collection.external import (
    ExternalCollectionResult,
)
from vikat_hire.collection.registry import (
    ExternalCollectorRegistry,
    ExternalCollectorRegistryError,
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


class FakeGitHubCollector:
    def __init__(self) -> None:
        self.calls = 0

    def collect(
        self,
        *,
        source_input: ExternalSourceInput,
    ) -> ExternalCollectionResult:
        self.calls += 1

        provenance = Provenance(
            provenance_id="prov-github",
            source_type=SourceType.GITHUB,
            source_ref="github-source",
            source_uri=str(source_input.github_url),
            retrieved_at=datetime.now(UTC),
            observed_at=datetime.now(UTC),
            method=DerivationMethod.API,
            access_status=AccessStatus.AUTHORIZED,
        )

        source = CollectedSource(
            source_type=SourceType.GITHUB,
            source_ref="github-source",
            source_uri=str(source_input.github_url),
            access_status=AccessStatus.AUTHORIZED,
            status=CollectionStatus.COLLECTED,
            provenance_refs=(provenance.provenance_id,),
        )

        block = ExtractedTextBlock(
            block_id="github-block",
            source_type=SourceType.GITHUB,
            source_ref="github-source",
            text="Python FastAPI",
            extraction_kind=ExtractionKind.PLAIN_TEXT,
            provenance_refs=(provenance.provenance_id,),
        )

        return ExternalCollectionResult(
            source=source,
            provenances=(provenance,),
            extracted_blocks=(block,),
        )


def _source_input() -> ExternalSourceInput:
    return ExternalSourceInput(
        github_url="https://github.com/example",
    )


def test_registry_dispatches_to_registered_collector() -> None:
    collector = FakeGitHubCollector()
    registry = ExternalCollectorRegistry(
        {
            SourceType.GITHUB: collector,
        }
    )

    result = registry.collect(
        source_type=SourceType.GITHUB,
        source_input=_source_input(),
    )

    assert collector.calls == 1
    assert result.source.source_type is SourceType.GITHUB
    assert result.extracted_blocks[0].source_type is SourceType.GITHUB


def test_registry_reports_missing_collector() -> None:
    registry = ExternalCollectorRegistry({})

    with pytest.raises(
        ExternalCollectorRegistryError,
        match="no collector registered for github",
    ):
        registry.collect(
            source_type=SourceType.GITHUB,
            source_input=_source_input(),
        )


def test_registry_rejects_unsupported_source_type() -> None:
    registry = ExternalCollectorRegistry({})

    with pytest.raises(
        ExternalCollectorRegistryError,
        match="unsupported external source type",
    ):
        registry.collect(
            source_type=SourceType.JD_FILE,
            source_input=_source_input(),
        )


def test_registry_rejects_invalid_collector() -> None:
    with pytest.raises(
        ExternalCollectorRegistryError,
        match="must provide collect",
    ):
        ExternalCollectorRegistry(
            {
                SourceType.GITHUB: object(),
            }
        )


def test_registry_rejects_collector_result_for_wrong_source() -> None:
    class WrongCollector:
        def collect(
            self,
            *,
            source_input: ExternalSourceInput,
        ) -> ExternalCollectionResult:
            provenance = Provenance(
                provenance_id="prov-linkedin",
                source_type=SourceType.LINKEDIN,
                source_ref="linkedin-source",
                source_uri="https://linkedin.com/example",
                retrieved_at=datetime.now(UTC),
                observed_at=datetime.now(UTC),
                method=DerivationMethod.API,
                access_status=AccessStatus.AUTHORIZED,
            )

            source = CollectedSource(
                source_type=SourceType.LINKEDIN,
                source_ref="linkedin-source",
                source_uri="https://linkedin.com/example",
                access_status=AccessStatus.AUTHORIZED,
                status=CollectionStatus.COLLECTED,
                provenance_refs=(provenance.provenance_id,),
            )

            block = ExtractedTextBlock(
                block_id="linkedin-block",
                source_type=SourceType.LINKEDIN,
                source_ref="linkedin-source",
                text="Software Engineer",
                extraction_kind=ExtractionKind.PLAIN_TEXT,
                provenance_refs=(provenance.provenance_id,),
            )

            return ExternalCollectionResult(
                source=source,
                provenances=(provenance,),
                extracted_blocks=(block,),
            )

    registry = ExternalCollectorRegistry(
        {
            SourceType.GITHUB: WrongCollector(),
        }
    )

    with pytest.raises(
        ExternalCollectorRegistryError,
        match="returned linkedin",
    ):
        registry.collect(
            source_type=SourceType.GITHUB,
            source_input=_source_input(),
        )


def test_registry_reports_registered_source_without_collecting_other_sources() -> None:
    collector = FakeGitHubCollector()

    registry = ExternalCollectorRegistry(
        {
            SourceType.GITHUB: collector,
        }
    )

    assert registry.has_collector(SourceType.GITHUB) is True
    assert registry.has_collector(SourceType.LINKEDIN) is False
    assert registry.has_collector(SourceType.PORTFOLIO) is False