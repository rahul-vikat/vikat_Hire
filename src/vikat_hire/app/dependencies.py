from __future__ import annotations

from vikat_hire.collection.apify_linkedin import ApifyLinkedInFetcher
from vikat_hire.collection.github import GitHubCollector, GitHubFetcher
from vikat_hire.collection.linkedin import LinkedInCollector
from vikat_hire.collection.portfolio import PortfolioCollector, PortfolioFetcher
from vikat_hire.collection.registry import ExternalCollectorRegistry
from vikat_hire.contracts.common import SourceType


class ApplicationDependencyError(ValueError):
    """Raised when application dependency construction is invalid."""


def build_linkedin_fetcher(
    *,
    apify_api_token: str,
    apify_actor_id: str,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 1.0,
) -> ApifyLinkedInFetcher:
    """
    Build the current LinkedIn retrieval provider.

    Apify configuration enters only at the application boundary.
    No domain contract or orchestration component depends on Apify.
    """
    if not isinstance(apify_api_token, str) or not apify_api_token.strip():
        raise ApplicationDependencyError(
            "Apify API token must be a non-empty string"
        )

    if not isinstance(apify_actor_id, str) or not apify_actor_id.strip():
        raise ApplicationDependencyError(
            "Apify actor ID must be a non-empty string"
        )

    return ApifyLinkedInFetcher(
        api_token=apify_api_token,
        actor_id=apify_actor_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )


def build_external_collector_registry(
    *,
    linkedin_fetcher,
    github_fetcher: GitHubFetcher,
    portfolio_fetcher: PortfolioFetcher,
) -> ExternalCollectorRegistry:
    """
    Build the provider-neutral external collection registry.

    Concrete retrieval providers are injected here. The registry itself
    remains unaware of their implementation details.
    """
    if not callable(getattr(linkedin_fetcher, "fetch", None)):
        raise ApplicationDependencyError(
            "LinkedIn fetcher must provide fetch()"
        )

    if not callable(getattr(github_fetcher, "fetch", None)):
        raise ApplicationDependencyError(
            "GitHub fetcher must provide fetch()"
        )

    if not callable(getattr(portfolio_fetcher, "fetch", None)):
        raise ApplicationDependencyError(
            "Portfolio fetcher must provide fetch()"
        )

    return ExternalCollectorRegistry(
        {
            SourceType.LINKEDIN: LinkedInCollector(linkedin_fetcher),
            SourceType.GITHUB: GitHubCollector(github_fetcher),
            SourceType.PORTFOLIO: PortfolioCollector(portfolio_fetcher),
        }
    )