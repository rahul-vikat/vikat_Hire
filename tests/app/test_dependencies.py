from __future__ import annotations

import pytest

from vikat_hire.app.dependencies import (
    ApplicationDependencyError,
    build_external_collector_registry,
    build_linkedin_fetcher,
)
from vikat_hire.collection.apify_linkedin import ApifyLinkedInFetcher
from vikat_hire.contracts.common import SourceType


class FakeFetcher:
    def fetch(self, *, url: str) -> str:
        return "example content"


def test_build_linkedin_fetcher_uses_injected_apify_configuration() -> None:
    fetcher = build_linkedin_fetcher(
        apify_api_token="test-token",
        apify_actor_id="example/linkedin-actor",
        timeout_seconds=15.0,
        poll_interval_seconds=0.5,
    )

    assert isinstance(fetcher, ApifyLinkedInFetcher)
    assert fetcher.api_token == "test-token"
    assert fetcher.actor_id == "example/linkedin-actor"
    assert fetcher.timeout_seconds == 15.0
    assert fetcher.poll_interval_seconds == 0.5


@pytest.mark.parametrize(
    ("api_token", "actor_id", "message"),
    [
        ("", "example/linkedin-actor", "API token"),
        ("   ", "example/linkedin-actor", "API token"),
        ("test-token", "", "actor ID"),
        ("test-token", "   ", "actor ID"),
    ],
)
def test_build_linkedin_fetcher_rejects_invalid_configuration(
    api_token: str,
    actor_id: str,
    message: str,
) -> None:
    with pytest.raises(
        ApplicationDependencyError,
        match=message,
    ):
        build_linkedin_fetcher(
            apify_api_token=api_token,
            apify_actor_id=actor_id,
        )


def test_build_external_collector_registry_registers_all_external_sources() -> None:
    registry = build_external_collector_registry(
        linkedin_fetcher=FakeFetcher(),
        github_fetcher=FakeFetcher(),
        portfolio_fetcher=FakeFetcher(),
    )

    assert registry.has_collector(SourceType.LINKEDIN) is True
    assert registry.has_collector(SourceType.GITHUB) is True
    assert registry.has_collector(SourceType.PORTFOLIO) is True


@pytest.mark.parametrize(
    "argument",
    [
        "linkedin_fetcher",
        "github_fetcher",
        "portfolio_fetcher",
    ],
)
def test_build_external_collector_registry_rejects_invalid_fetcher(
    argument: str,
) -> None:
    kwargs = {
        "linkedin_fetcher": FakeFetcher(),
        "github_fetcher": FakeFetcher(),
        "portfolio_fetcher": FakeFetcher(),
    }
    kwargs[argument] = object()

    with pytest.raises(
        ApplicationDependencyError,
        match="fetch",
    ):
        build_external_collector_registry(**kwargs)