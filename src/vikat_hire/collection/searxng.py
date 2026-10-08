"""SearXNG raw search collection; no entity validation or evaluation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from os import environ
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from vikat_hire.config.research_queries import get_research_query
from vikat_hire.contracts.common import (
    AccessStatus,
    DerivationMethod,
    Provenance,
    SourceType,
)
from vikat_hire.contracts.research import (
    RawResearchResult,
    ResearchDimension,
    ResearchEntityType,
    ResearchSearchBatch,
)


class SearXNGCollectionError(RuntimeError):
    """Base error for SearXNG transport or response validation failures."""


class SearXNGUnavailableError(SearXNGCollectionError):
    """SearXNG could not be reached or returned an unsuccessful HTTP status."""


class SearXNGMalformedResponseError(SearXNGCollectionError):
    """SearXNG returned JSON outside the supported response shape."""


@dataclass(frozen=True)
class SearXNGConfiguration:
    base_url: str
    timeout_seconds: float = 15.0
    max_results: int = 20

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> SearXNGConfiguration:
        values = environ if environment is None else environment
        required = (
            "SEARXNG_BASE_URL",
            "VIKATHIRE_SEARXNG_TIMEOUT_SECONDS",
            "VIKATHIRE_SEARXNG_MAX_RESULTS",
        )
        missing = tuple(name for name in required if not values.get(name, "").strip())
        if missing:
            raise ValueError(
                "missing SearXNG environment configuration: "
                + ", ".join(missing)
            )
        try:
            timeout_seconds = float(values[required[1]])
            max_results = int(values[required[2]])
        except ValueError as exc:
            raise ValueError(
                "SearXNG timeout and max-results settings must be numeric"
            ) from exc
        return cls(
            base_url=values[required[0]],
            timeout_seconds=timeout_seconds,
            max_results=max_results,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            raise ValueError("SearXNG base_url must not be blank")
        if self.timeout_seconds <= 0:
            raise ValueError("SearXNG timeout_seconds must be greater than zero")
        if self.max_results <= 0:
            raise ValueError("SearXNG max_results must be greater than zero")
        parts = urlsplit(self.base_url.strip())
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("SearXNG base_url must be an HTTP(S) URL")

    @property
    def search_url(self) -> str:
        parts = urlsplit(self.base_url.strip())
        path = parts.path.rstrip("/")
        if not path.endswith("/search"):
            path = f"{path}/search" if path else "/search"
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


class SearXNGClient:
    """Fetch and parse raw SearXNG results, preserving query provenance."""

    def __init__(
        self,
        configuration: SearXNGConfiguration,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(configuration, SearXNGConfiguration):
            raise TypeError("configuration must be SearXNGConfiguration")
        self._configuration = configuration
        self._transport = transport

    def search(
        self,
        *,
        entity_type: ResearchEntityType,
        entity_name: str,
        dimension: ResearchDimension,
    ) -> ResearchSearchBatch:
        query = get_research_query(
            entity_type=entity_type,
            dimension=dimension,
            entity_name=entity_name,
        )
        try:
            with httpx.Client(
                timeout=self._configuration.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.get(
                    self._configuration.search_url,
                    params={
                        "q": query,
                        "format": "json",
                        "language": "en",
                        "categories": "general",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise SearXNGUnavailableError("SearXNG request failed") from exc
        except ValueError as exc:
            raise SearXNGMalformedResponseError(
                "SearXNG response was not valid JSON"
            ) from exc

        return self.parse_response(
            payload,
            entity_type=entity_type,
            entity_name=entity_name,
            dimension=dimension,
            requested_query=query,
        )

    def parse_response(
        self,
        payload: Any,
        *,
        entity_type: ResearchEntityType,
        entity_name: str,
        dimension: ResearchDimension,
        requested_query: str,
    ) -> ResearchSearchBatch:
        if not isinstance(payload, dict):
            raise SearXNGMalformedResponseError(
                "SearXNG response must be a JSON object"
            )
        response_query = payload.get("query")
        raw_results = payload.get("results")
        if not isinstance(response_query, str) or not response_query.strip():
            raise SearXNGMalformedResponseError(
                "SearXNG response query must be a non-blank string"
            )
        if response_query != requested_query:
            raise SearXNGMalformedResponseError(
                "SearXNG response query does not match requested query"
            )
        if not isinstance(raw_results, list):
            raise SearXNGMalformedResponseError(
                "SearXNG response results must be a list"
            )

        results: list[RawResearchResult] = []
        provenances: list[Provenance] = []
        retrieved_at = datetime.now(UTC)
        for result_index, raw in enumerate(
            raw_results[: self._configuration.max_results]
        ):
            if not isinstance(raw, dict):
                raise SearXNGMalformedResponseError(
                    f"SearXNG results[{result_index}] must be an object"
                )
            title = raw.get("title")
            url = raw.get("url")
            content = raw.get("content")
            if not all(isinstance(value, str) for value in (title, url, content)):
                raise SearXNGMalformedResponseError(
                    "SearXNG result title, url, and content must be strings"
                )

            result_id = _result_id(
                entity_type=entity_type,
                entity_name=entity_name,
                dimension=dimension,
                query=requested_query,
                result_index=result_index,
                url=url,
                content=content,
            )
            provenance = Provenance(
                source_type=SourceType.SEARXNG,
                provenance_id=f"{result_id}:provenance",
                source_ref=result_id,
                source_uri=url,
                retrieved_at=retrieved_at,
                locator={
                    "entity_type": entity_type.value,
                    "entity_name": entity_name,
                    "dimension": dimension.value,
                    "query": requested_query,
                    "result_index": str(result_index),
                },
                excerpt=content,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                method=DerivationMethod.API,
                access_status=AccessStatus.PUBLIC,
            )
            results.append(
                RawResearchResult(
                    result_id=result_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    dimension=dimension,
                    query=requested_query,
                    result_index=result_index,
                    title=title,
                    url=url,
                    content=content,
                    provenance_refs=(provenance.provenance_id,),
                )
            )
            provenances.append(provenance)

        try:
            return ResearchSearchBatch(
                entity_type=entity_type,
                entity_name=entity_name,
                dimension=dimension,
                query=requested_query,
                results=tuple(results),
                provenances=tuple(provenances),
            )
        except (TypeError, ValueError) as exc:
            raise SearXNGMalformedResponseError(
                f"invalid SearXNG result batch: {exc}"
            ) from exc


def _result_id(
    *,
    entity_type: ResearchEntityType,
    entity_name: str,
    dimension: ResearchDimension,
    query: str,
    result_index: int,
    url: str,
    content: str,
) -> str:
    raw = "\x1f".join(
        (
            entity_type.value,
            entity_name,
            dimension.value,
            query,
            str(result_index),
            url,
            content,
        )
    )
    return "research-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
