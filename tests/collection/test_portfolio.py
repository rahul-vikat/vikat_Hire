from __future__ import annotations

import pytest

from vikat_hire.collection.portfolio import (
    PortfolioCollectionError,
    PortfolioCollector,
)
from vikat_hire.contracts.collection import CollectionStatus
from vikat_hire.contracts.common import (
    AccessStatus,
    DerivationMethod,
    SourceType,
)
from vikat_hire.contracts.inputs import ExternalSourceInput
from vikat_hire.contracts.normalization import ExtractionKind


class FakePortfolioFetcher:
    def __init__(
        self,
        text: str = "Portfolio project content",
    ) -> None:
        self.text = text
        self.urls: list[str] = []

    def fetch(self, *, url: str) -> str:
        self.urls.append(url)
        return self.text


def _input(
    *,
    url: str | None = "https://portfolio.example",
    authorized: bool = True,
) -> ExternalSourceInput:
    return ExternalSourceInput(
        portfolio_url=url,
        portfolio_authorized=authorized,
    )


def test_collects_authorized_portfolio_source() -> None:
    fetcher = FakePortfolioFetcher()
    collector = PortfolioCollector(fetcher)

    result = collector.collect(
        source_input=_input(),
    )

    assert fetcher.urls == ["https://portfolio.example/"]
    assert result.source.source_type is SourceType.PORTFOLIO
    assert result.source.status == CollectionStatus.COLLECTED
    assert result.source.access_status is AccessStatus.AUTHORIZED
    assert len(result.extracted_blocks) == 1
    assert result.extracted_blocks[0].source_type is SourceType.PORTFOLIO
    assert result.extracted_blocks[0].text == "Portfolio project content"
    assert result.extracted_blocks[0].extraction_kind is ExtractionKind.PLAIN_TEXT
    assert len(result.provenances) == 1
    assert result.provenances[0].source_type is SourceType.PORTFOLIO
    assert result.provenances[0].method is DerivationMethod.CRAWLER
    assert result.provenances[0].content_hash is not None


def test_does_not_fetch_missing_portfolio_url() -> None:
    fetcher = FakePortfolioFetcher()
    collector = PortfolioCollector(fetcher)

    result = collector.collect(
        source_input=_input(url=None),
    )

    assert fetcher.urls == []
    assert result.source.status == CollectionStatus.NOT_APPLICABLE
    assert result.source.access_status is None
    assert result.extracted_blocks == ()
    assert result.provenances == ()


def test_does_not_fetch_unauthorized_portfolio_source() -> None:
    fetcher = FakePortfolioFetcher()
    collector = PortfolioCollector(fetcher)

    result = collector.collect(
        source_input=_input(authorized=False),
    )

    assert fetcher.urls == []
    assert result.source.status == CollectionStatus.NOT_AUTHORIZED
    assert result.source.access_status is AccessStatus.NOT_AUTHORIZED
    assert result.extracted_blocks == ()
    assert len(result.provenances) == 1
    assert result.provenances[0].access_status is AccessStatus.NOT_AUTHORIZED
    assert result.provenances[0].method is DerivationMethod.RULE


def test_rejects_empty_fetched_content() -> None:
    fetcher = FakePortfolioFetcher(text="   ")
    collector = PortfolioCollector(fetcher)

    with pytest.raises(
        PortfolioCollectionError,
        match="returned empty content",
    ):
        collector.collect(
            source_input=_input(),
        )


def test_rejects_non_string_fetched_content() -> None:
    class InvalidFetcher:
        def fetch(self, *, url: str) -> str:
            return 123  # type: ignore[return-value]

    collector = PortfolioCollector(InvalidFetcher())

    with pytest.raises(
        PortfolioCollectionError,
        match="must return text",
    ):
        collector.collect(
            source_input=_input(),
        )


def test_source_reference_is_derived_from_external_input_identity() -> None:
    fetcher = FakePortfolioFetcher()
    collector = PortfolioCollector(fetcher)

    source_input = _input()

    result = collector.collect(
        source_input=source_input,
    )

    assert result.source.source_ref == (
        f"portfolio-{source_input.input_id}"
    )
    assert result.provenances[0].source_ref == result.source.source_ref
    assert result.extracted_blocks[0].source_ref == result.source.source_ref


def test_content_hash_is_deterministic_for_same_content() -> None:
    first = PortfolioCollector(
        FakePortfolioFetcher(text="same portfolio content"),
    ).collect(
        source_input=_input(),
    )

    second = PortfolioCollector(
        FakePortfolioFetcher(text="same portfolio content"),
    ).collect(
        source_input=_input(),
    )

    assert (
        first.provenances[0].content_hash
        == second.provenances[0].content_hash
    )


def test_collector_requires_fetcher() -> None:
    with pytest.raises(
        PortfolioCollectionError,
        match="must provide fetch",
    ):
        PortfolioCollector(object())
