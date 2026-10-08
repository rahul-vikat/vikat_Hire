from __future__ import annotations

import io
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
    _request_public_page,
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
        requester=_portfolio_response(
            200,
            {"content-type": "text/html; charset=utf-8"},
            b"<h1>Portfolio</h1><p>Built services</p><script>secret</script>",
        ),
        resolver=_public_resolver,
    )

    result = fetcher.fetch(url="https://portfolio.example")

    assert result == "Portfolio\nBuilt services"
    assert "secret" not in result


def test_portfolio_redirect_to_private_address_is_rejected() -> None:
    calls: list[str] = []

    def requester(url: str, address: str, timeout: float, max_bytes: int):
        calls.append(url)
        return 302, {"location": "http://127.0.0.1/admin"}, b""

    fetcher = HTTPPortfolioTextFetcher(
        requester=requester,
        resolver=_public_resolver,
    )

    with pytest.raises(ProviderMalformedResponseError, match="publicly routable"):
        fetcher.fetch(url="https://portfolio.example")
    assert calls == ["https://portfolio.example"]


def test_portfolio_response_size_is_bounded() -> None:
    fetcher = HTTPPortfolioTextFetcher(
        max_bytes=8,
        requester=_portfolio_response(
            200,
            {"content-type": "text/plain"},
            b"too much content",
        ),
        resolver=_public_resolver,
    )

    with pytest.raises(ProviderMalformedResponseError, match="byte limit"):
        fetcher.fetch(url="https://portfolio.example")


def test_portfolio_timeout_is_translated() -> None:
    def requester(url: str, address: str, timeout: float, max_bytes: int):
        raise ProviderUnavailableError("portfolio request timed out")

    fetcher = HTTPPortfolioTextFetcher(
        requester=requester,
        resolver=_public_resolver,
    )

    with pytest.raises(ProviderUnavailableError, match="timed out"):
        fetcher.fetch(url="https://portfolio.example")


def test_portfolio_server_failure_is_unavailable() -> None:
    fetcher = HTTPPortfolioTextFetcher(
        requester=_portfolio_response(503, {}, b""),
        resolver=_public_resolver,
    )

    with pytest.raises(ProviderUnavailableError, match="unavailable"):
        fetcher.fetch(url="https://portfolio.example")


def test_portfolio_unsupported_content_type_is_rejected() -> None:
    fetcher = HTTPPortfolioTextFetcher(
        requester=_portfolio_response(200, {"content-type": "application/pdf"}, b"%PDF"),
        resolver=_public_resolver,
    )

    with pytest.raises(ProviderMalformedResponseError, match="HTML or plain text"):
        fetcher.fetch(url="https://portfolio.example")


def test_portfolio_dns_result_is_pinned_and_credentials_are_rejected() -> None:
    seen: list[tuple[str, str]] = []

    def requester(url: str, address: str, timeout: float, max_bytes: int):
        seen.append((url, address))
        return 200, {"content-type": "text/plain"}, b"Portfolio"

    fetcher = HTTPPortfolioTextFetcher(
        requester=requester,
        resolver=_public_resolver,
    )
    assert fetcher.fetch(url="https://portfolio.example") == "Portfolio"
    assert seen == [("https://portfolio.example", "8.8.8.8")]

    with pytest.raises(ProviderMalformedResponseError, match="credentials"):
        fetcher.fetch(url="https://user:secret@portfolio.example")


def test_portfolio_rejects_mixed_public_and_private_dns_answers() -> None:
    def resolver(host: str, port: int) -> list[tuple]:
        return socket.getaddrinfo("8.8.8.8", port) + socket.getaddrinfo("127.0.0.1", port)

    fetcher = HTTPPortfolioTextFetcher(
        requester=_portfolio_response(200, {"content-type": "text/plain"}, b"x"),
        resolver=resolver,
    )

    with pytest.raises(ProviderMalformedResponseError, match="non-public"):
        fetcher.fetch(url="https://portfolio.example")


def test_portfolio_connection_uses_the_validated_ip_and_original_host(monkeypatch) -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.sent = bytearray()

        def sendall(self, data: bytes) -> None:
            self.sent.extend(data)

        def makefile(self, mode: str, buffering: int | None = None):
            return io.BytesIO(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 4\r\n\r\nTest"
            )

        def close(self) -> None:
            pass

    fake_socket = FakeSocket()
    connections: list[tuple[tuple[str, int], float | None]] = []

    def connect(address, timeout):
        connections.append((address, timeout))
        return fake_socket

    monkeypatch.setattr("vikat_hire.collection.http_providers.socket.create_connection", connect)

    status, headers, body = _request_public_page(
        "http://portfolio.example/path",
        "8.8.8.8",
        2.0,
        100,
    )

    assert status == 200
    assert headers["content-type"] == "text/plain"
    assert body == b"Test"
    assert connections == [(("8.8.8.8", 80), 2.0)]
    request_text = fake_socket.sent.decode("ascii")
    assert "Host: portfolio.example" in request_text
    assert "Host: 8.8.8.8" not in request_text


def _public_resolver(host: str, port: int) -> list[tuple]:
    return socket.getaddrinfo(str(ipaddress.ip_address("8.8.8.8")), port)


def _portfolio_response(status: int, headers: dict[str, str], body: bytes):
    def request(url: str, address: str, timeout: float, max_bytes: int):
        return status, headers, body

    return request
