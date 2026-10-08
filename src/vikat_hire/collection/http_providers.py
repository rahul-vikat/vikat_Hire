from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx


class ProviderFetchError(RuntimeError):
    """Base class for production external-provider failures."""


class ProviderAuthenticationError(ProviderFetchError):
    """The provider rejected the configured credentials."""


class ProviderUnavailableError(ProviderFetchError):
    """The provider could not be reached or returned a server error."""


class ProviderMalformedResponseError(ProviderFetchError):
    """The provider response did not match the supported response shape."""


class GitHubAPITextFetcher:
    """Fetch public GitHub profile or repository facts through GitHub REST."""

    _API_BASE = "https://api.github.com"

    def __init__(
        self,
        *,
        token: str | None,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self._token = token.strip() if token and token.strip() else None
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def fetch(self, *, url: str) -> str:
        owner, repository = _github_path(url)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "VikatHire/1.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            with httpx.Client(
                timeout=self._timeout_seconds,
                transport=self._transport,
                headers=headers,
            ) as client:
                if repository:
                    payload = self._get_json(client, f"/repos/{owner}/{repository}")
                    return _repository_text(payload)
                profile = self._get_json(client, f"/users/{owner}")
                repos = self._get_json(
                    client,
                    f"/users/{owner}/repos?per_page=100&type=owner&sort=updated",
                )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError("GitHub request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("GitHub request failed") from exc

        if not isinstance(repos, list) or any(not isinstance(item, dict) for item in repos):
            raise ProviderMalformedResponseError("GitHub repositories response must be a list")
        return _profile_text(profile, repos)

    @staticmethod
    def _get_json(client: httpx.Client, path: str):
        response = client.get(f"{GitHubAPITextFetcher._API_BASE}{path}")
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError(
                "GitHub rejected authentication or rate limited access"
            )
        if response.status_code == 404:
            raise ProviderMalformedResponseError("GitHub account or repository was not found")
        if response.status_code >= 500:
            raise ProviderUnavailableError("GitHub service is unavailable")
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderMalformedResponseError("GitHub response was not valid JSON") from exc


def _github_path(url: str) -> tuple[str, str | None]:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"github.com", "www.github.com"}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ProviderMalformedResponseError("GitHub URL must use the github.com HTTPS host")
    parts = [part for part in parsed.path.split("/") if part]
    if not parts or len(parts) > 2 or any(part in {".", ".."} for part in parts):
        raise ProviderMalformedResponseError(
            "GitHub URL must identify a user, organization, or repository"
        )
    return parts[0], parts[1] if len(parts) == 2 else None


def _profile_text(profile: object, repos: list[dict]) -> str:
    if not isinstance(profile, dict):
        raise ProviderMalformedResponseError("GitHub profile response must be an object")
    facts: list[str] = []
    for label, key in (
        ("Account", "login"),
        ("Name", "name"),
        ("Bio", "bio"),
        ("Public repositories", "public_repos"),
    ):
        value = profile.get(key)
        if value not in (None, ""):
            facts.append(f"{label}: {value}")
    for repo in sorted(repos, key=lambda item: str(item.get("full_name", "")).casefold()):
        facts.extend(_repository_lines(repo))
    if not facts:
        raise ProviderMalformedResponseError("GitHub returned no usable profile or repository data")
    return "\n".join(facts)


def _repository_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ProviderMalformedResponseError("GitHub repository response must be an object")
    lines = _repository_lines(payload)
    if not lines:
        raise ProviderMalformedResponseError("GitHub returned no usable repository data")
    return "\n".join(lines)


def _repository_lines(repo: dict) -> list[str]:
    lines: list[str] = []
    for label, key in (
        ("Repository", "full_name"),
        ("Description", "description"),
        ("Primary language", "language"),
        ("Topics", "topics"),
        ("Repository URL", "html_url"),
    ):
        value = repo.get(key)
        if value not in (None, "", []):
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            lines.append(f"{label}: {value}")
    return lines


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.casefold() in {"script", "style", "noscript", "svg"}:
            self._hidden_depth += 1
        elif tag.casefold() in {"p", "div", "li", "h1", "h2", "h3", "br", "section", "article"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript", "svg"} and self._hidden_depth:
            self._hidden_depth -= 1
        elif tag.casefold() in {"p", "div", "li", "h1", "h2", "h3", "section", "article"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


class HTTPPortfolioTextFetcher:
    """Fetch a public portfolio page and return its visible text only."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        max_bytes: int = 5 * 1024 * 1024,
        max_redirects: int = 3,
        transport: httpx.BaseTransport | None = None,
        resolver: Callable[[str, int], list[tuple]] | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_bytes <= 0 or max_redirects < 0:
            raise ValueError("portfolio timeout/size/redirect limits are invalid")
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._transport = transport
        self._resolver = resolver or socket.getaddrinfo

    def fetch(self, *, url: str) -> str:
        current_url = _validate_public_http_url(url, resolver=self._resolver)
        try:
            with httpx.Client(
                timeout=self._timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
                headers={"Accept": "text/html,application/xhtml+xml,text/plain"},
            ) as client:
                for redirect_count in range(self._max_redirects + 1):
                    with client.stream("GET", current_url) as response:
                        if response.is_redirect:
                            if redirect_count >= self._max_redirects:
                                raise ProviderUnavailableError("portfolio exceeded redirect limit")
                            location = response.headers.get("location")
                            if not location:
                                raise ProviderMalformedResponseError(
                                    "portfolio redirect omitted Location"
                                )
                            current_url = _validate_public_http_url(
                                urljoin(current_url, location),
                                resolver=self._resolver,
                            )
                            continue
                        if response.status_code == 401 or response.status_code == 403:
                            raise ProviderAuthenticationError("portfolio denied access")
                        if response.status_code >= 500:
                            raise ProviderUnavailableError("portfolio service is unavailable")
                        response.raise_for_status()
                        content_type = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .casefold()
                        )
                        if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                            raise ProviderMalformedResponseError(
                                "portfolio response must be HTML or plain text"
                            )
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            body.extend(chunk)
                            if len(body) > self._max_bytes:
                                raise ProviderMalformedResponseError(
                                    "portfolio response exceeds configured byte limit"
                                )
                        encoding = response.encoding or "utf-8"
                        raw_text = bytes(body).decode(encoding, errors="replace")
                        if content_type == "text/plain":
                            visible_text = raw_text
                        else:
                            parser = _VisibleTextParser()
                            parser.feed(raw_text)
                            visible_text = "".join(parser.parts)
                        normalized = "\n".join(
                            line.strip() for line in visible_text.splitlines() if line.strip()
                        )
                        if not normalized:
                            raise ProviderMalformedResponseError(
                                "portfolio page contains no visible text"
                            )
                        return normalized
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError("portfolio request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("portfolio request failed") from exc
        raise ProviderUnavailableError("portfolio request did not produce a response")


def _validate_public_http_url(
    url: str,
    *,
    resolver: Callable[[str, int], list[tuple]],
) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProviderMalformedResponseError("portfolio URL must be HTTP(S)")
    host = parsed.hostname.rstrip(".").casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ProviderMalformedResponseError("portfolio URL host must be publicly routable")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if not address.is_global:
            raise ProviderMalformedResponseError("portfolio URL host must be publicly routable")
    else:
        try:
            resolved = resolver(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
            )
        except OSError as exc:
            raise ProviderUnavailableError("portfolio host could not be resolved") from exc
        if not resolved or any(not ipaddress.ip_address(item[4][0]).is_global for item in resolved):
            raise ProviderMalformedResponseError(
                "portfolio URL host resolves to a non-public address"
            )
    return url
