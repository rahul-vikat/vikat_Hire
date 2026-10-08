from __future__ import annotations

import ipaddress
import socket

import httpx
import pytest

from vikat_hire.collection.http_providers import (
    GitHubAPITextFetcher,
    HTTPPortfolioTextFetcher,
    ProviderAuthenticationError,
    ProviderMalformedResponseError,
    ProviderUnavailableError,
)


def test_github_profile_fetch_returns_deterministic_factual_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users/octocat":
            return httpx.Response(
                200,
                json={
                    "login": "octocat",
                    "name": "Octo Cat",
                    "bio": "Builds APIs",
                    "public_repos": 1,
                },
            )
        return httpx.Response(
            200,
            json=[
                {
                    "full_name": "octocat/sample",
                    "description": "Example API service",
                    "language": "Python",
                    "topics": ["api"],
                    "html_url": "https://github.com/octocat/sample",
                }
            ],
        )

    fetcher = GitHubAPITextFetcher(
        token="test-token",
        transport=httpx.MockTransport(handler),
    )

    first = fetcher.fetch(url="https://github.com/octocat")
    second = fetcher.fetch(url="https://github.com/octocat")

    assert first == second
    assert "Repository: octocat/sample" in first
    assert "Primary language: Python" in first


def test_github_rejects_non_github_target() -> None:
    fetcher = GitHubAPITextFetcher(
        token=None,
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
    )

    with pytest.raises(ProviderMalformedResponseError, match="github.com"):
        fetcher.fetch(url="https://github.com.evil.example/octocat")


def test_github_authentication_failure_is_explicit() -> None:
    fetcher = GitHubAPITextFetcher(
        token="wrong-token",
        transport=httpx.MockTransport(lambda _: httpx.Response(401)),
    )

    with pytest.raises(ProviderAuthenticationError):
        fetcher.fetch(url="https://github.com/octocat/sample")


def test_github_timeout_is_translated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    fetcher = GitHubAPITextFetcher(token=None, transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderUnavailableError, match="timed out"):
        fetcher.fetch(url="https://github.com/octocat/sample")


def test_github_server_failure_is_unavailable() -> None:
    fetcher = GitHubAPITextFetcher(
        token=None,
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    )

    with pytest.raises(ProviderUnavailableError, match="unavailable"):
        fetcher.fetch(url="https://github.com/octocat/sample")


def test_github_malformed_json_is_rejected() -> None:
    fetcher = GitHubAPITextFetcher(
        token=None,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"not-json")),
    )

    with pytest.raises(ProviderMalformedResponseError, match="valid JSON"):
        fetcher.fetch(url="https://github.com/octocat/sample")


def test_portfolio_html_is_reduced_to_visible_text() -> None:
    fetcher = HTTPPortfolioTextFetcher(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<h1>Portfolio</h1><p>Built services</p><script>secret</script>",
            )
        ),
        resolver=_public_resolver,
    )

    result = fetcher.fetch(url="https://portfolio.example")

    assert result == "Portfolio\nBuilt services"
    assert "secret" not in result


def test_portfolio_redirect_to_private_address_is_rejected() -> None:
    fetcher = HTTPPortfolioTextFetcher(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
        ),
        resolver=_public_resolver,
    )

    with pytest.raises(ProviderMalformedResponseError, match="publicly routable"):
        fetcher.fetch(url="https://portfolio.example")


def test_portfolio_response_size_is_bounded() -> None:
    fetcher = HTTPPortfolioTextFetcher(
        max_bytes=8,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="too much content",
            )
        ),
        resolver=_public_resolver,
    )

    with pytest.raises(ProviderMalformedResponseError, match="byte limit"):
        fetcher.fetch(url="https://portfolio.example")


def test_portfolio_timeout_is_translated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    fetcher = HTTPPortfolioTextFetcher(
        transport=httpx.MockTransport(handler),
        resolver=_public_resolver,
    )

    with pytest.raises(ProviderUnavailableError, match="timed out"):
        fetcher.fetch(url="https://portfolio.example")


def test_portfolio_server_failure_is_unavailable() -> None:
    fetcher = HTTPPortfolioTextFetcher(
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
        resolver=_public_resolver,
    )

    with pytest.raises(ProviderUnavailableError, match="unavailable"):
        fetcher.fetch(url="https://portfolio.example")


def test_portfolio_unsupported_content_type_is_rejected() -> None:
    fetcher = HTTPPortfolioTextFetcher(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=b"%PDF",
            )
        ),
        resolver=_public_resolver,
    )

    with pytest.raises(ProviderMalformedResponseError, match="HTML or plain text"):
        fetcher.fetch(url="https://portfolio.example")


def _public_resolver(host: str, port: int) -> list[tuple]:
    return socket.getaddrinfo(str(ipaddress.ip_address("8.8.8.8")), port)
