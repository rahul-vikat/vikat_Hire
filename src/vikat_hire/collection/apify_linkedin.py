from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


class ApifyLinkedInError(RuntimeError):
    """Base error for Apify-backed LinkedIn retrieval."""


class ApifyConfigurationError(ApifyLinkedInError):
    """Apify credentials or actor configuration are missing."""


class InvalidLinkedInUrlError(ApifyLinkedInError):
    """The supplied URL is not a valid LinkedIn profile URL."""


class ApifyAuthenticationError(ApifyLinkedInError):
    """Apify rejected the configured credentials."""


class ApifyActorNotFoundError(ApifyLinkedInError):
    """The configured Apify actor or actor run was not found."""


class ApifyActorExecutionError(ApifyLinkedInError):
    """The Apify actor failed to execute successfully."""


class ApifyTimeoutError(ApifyLinkedInError):
    """The Apify actor did not finish within the configured timeout."""


class ApifyMalformedResponseError(ApifyLinkedInError):
    """Apify returned a response that does not satisfy the expected contract."""


class ApifyServiceUnavailableError(ApifyLinkedInError):
    """Apify returned a server-side failure."""


@dataclass(frozen=True)
class ApifyLinkedInFetcher:
    """
    Concrete LinkedInFetcher implementation backed by the Apify REST API.

    This adapter owns all Apify-specific retrieval mechanics. It returns
    deterministic JSON text so the existing provider-neutral LinkedInCollector
    can continue to own source/provenance/extraction contracts.
    """

    api_token: str
    actor_id: str
    timeout_seconds: float = 30.0
    poll_interval_seconds: float = 1.0
    transport: httpx.BaseTransport | None = None

    def __post_init__(self) -> None:
        if not self.api_token.strip():
            raise ApifyConfigurationError(
                "Apify API token must not be blank"
            )

        if not self.actor_id.strip():
            raise ApifyConfigurationError(
                "Apify LinkedIn actor ID must not be blank"
            )

        if self.timeout_seconds <= 0:
            raise ApifyConfigurationError(
                "Apify timeout_seconds must be greater than zero"
            )

        if self.poll_interval_seconds < 0:
            raise ApifyConfigurationError(
                "Apify poll_interval_seconds must not be negative"
            )

    def fetch(self, *, url: str) -> str:
        """
        Retrieve one LinkedIn profile through the configured Apify actor.

        The returned text is deterministic JSON containing the actor dataset
        items. No scoring, matching, normalization, or eligibility decision
        occurs here.
        """
        validated_url = self._validate_linkedin_url(url)

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        with httpx.Client(
            base_url="https://api.apify.com",
            headers=headers,
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            run_id, dataset_id, status = self._start_actor(
                client,
                linkedin_url=validated_url,
            )

            if status in {"READY", "RUNNING"}:
                status, dataset_id = self._poll_actor(
                    client,
                    run_id=run_id,
                    dataset_id=dataset_id,
                )

            if status != "SUCCEEDED":
                raise ApifyActorExecutionError(
                    f"Apify actor execution ended with status: {status}"
                )

            if not dataset_id:
                raise ApifyMalformedResponseError(
                    "Apify actor run did not provide a dataset ID"
                )

            items = self._fetch_dataset(
                client,
                dataset_id=dataset_id,
            )

        if not items:
            raise ApifyMalformedResponseError(
                "Apify LinkedIn dataset contained no profile items"
            )

        return json.dumps(
            items,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _start_actor(
        self,
        client: httpx.Client,
        *,
        linkedin_url: str,
    ) -> tuple[str, str | None, str]:
        payload = {
            "startUrls": [
                {
                    "url": linkedin_url,
                }
            ]
        }

        try:
            response = client.post(
                f"/v2/acts/{self.actor_id}/runs",
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise ApifyServiceUnavailableError(
                "failed to start Apify actor"
            ) from exc

        self._raise_for_apify_status(
            response,
            operation="actor startup",
        )

        body = self._parse_json_object(
            response,
            operation="actor startup",
        )

        run_data = body.get("data", body)

        if not isinstance(run_data, dict):
            raise ApifyMalformedResponseError(
                "Apify actor startup response data must be an object"
            )

        run_id = run_data.get("id")

        if not isinstance(run_id, str) or not run_id.strip():
            raise ApifyMalformedResponseError(
                "Apify actor startup response did not contain a run ID"
            )

        dataset_id = self._dataset_id(run_data)

        status = run_data.get("status", "RUNNING")

        if not isinstance(status, str):
            raise ApifyMalformedResponseError(
                "Apify actor startup response contained an invalid status"
            )

        return run_id, dataset_id, status

    def _poll_actor(
        self,
        client: httpx.Client,
        *,
        run_id: str,
        dataset_id: str | None,
    ) -> tuple[str, str | None]:
        started_at = time.monotonic()
        status = "RUNNING"

        while status in {"READY", "RUNNING"}:
            if time.monotonic() - started_at >= self.timeout_seconds:
                raise ApifyTimeoutError(
                    "Apify LinkedIn actor run timed out"
                )

            if self.poll_interval_seconds > 0:
                time.sleep(self.poll_interval_seconds)

            try:
                response = client.get(
                    f"/v2/actor-runs/{run_id}",
                )
            except httpx.HTTPError as exc:
                raise ApifyServiceUnavailableError(
                    "failed to poll Apify actor run"
                ) from exc

            self._raise_for_apify_status(
                response,
                operation="actor status polling",
            )

            body = self._parse_json_object(
                response,
                operation="actor status polling",
            )

            run_data = body.get("data", body)

            if not isinstance(run_data, dict):
                raise ApifyMalformedResponseError(
                    "Apify actor status response data must be an object"
                )

            status_value = run_data.get("status")

            if not isinstance(status_value, str):
                raise ApifyMalformedResponseError(
                    "Apify actor status response did not contain a valid status"
                )

            status = status_value
            dataset_id = (
                self._dataset_id(run_data)
                or dataset_id
            )

            if status in {
                "FAILED",
                "TIMED_OUT",
                "ABORTED",
                "CANCELLED",
            }:
                raise ApifyActorExecutionError(
                    f"Apify actor execution failed with status: {status}"
                )

        return status, dataset_id

    def _fetch_dataset(
        self,
        client: httpx.Client,
        *,
        dataset_id: str,
    ) -> list[dict[str, Any]]:
        try:
            response = client.get(
                f"/v2/datasets/{dataset_id}/items",
            )
        except httpx.HTTPError as exc:
            raise ApifyServiceUnavailableError(
                "failed to retrieve Apify dataset"
            ) from exc

        self._raise_for_apify_status(
            response,
            operation="dataset retrieval",
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ApifyMalformedResponseError(
                "Apify dataset response was not valid JSON"
            ) from exc

        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and isinstance(
            payload.get("items"),
            list,
        ):
            items = payload["items"]
        elif isinstance(payload, dict):
            items = [payload]
        else:
            raise ApifyMalformedResponseError(
                "Apify dataset response must be an object or list"
            )

        if any(not isinstance(item, dict) for item in items):
            raise ApifyMalformedResponseError(
                "Apify dataset items must all be objects"
            )

        return items

    @staticmethod
    def _dataset_id(data: dict[str, Any]) -> str | None:
        for key in ("defaultDatasetId", "datasetId"):
            value = data.get(key)

            if isinstance(value, str) and value.strip():
                return value

        return None

    @staticmethod
    def _parse_json_object(
        response: httpx.Response,
        *,
        operation: str,
    ) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApifyMalformedResponseError(
                f"Apify {operation} response was not valid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise ApifyMalformedResponseError(
                f"Apify {operation} response must be a JSON object"
            )

        return payload

    @staticmethod
    def _raise_for_apify_status(
        response: httpx.Response,
        *,
        operation: str,
    ) -> None:
        if response.status_code in {401, 403}:
            raise ApifyAuthenticationError(
                f"Apify authentication failed during {operation}"
            )

        if response.status_code == 404:
            raise ApifyActorNotFoundError(
                f"Apify resource was not found during {operation}"
            )

        if response.status_code >= 500:
            raise ApifyServiceUnavailableError(
                f"Apify service returned HTTP {response.status_code} during "
                f"{operation}"
            )

        if response.status_code >= 400:
            raise ApifyActorExecutionError(
                f"Apify returned HTTP {response.status_code} during "
                f"{operation}"
            )

    @staticmethod
    def _validate_linkedin_url(url: str) -> str:
        if not isinstance(url, str) or not url.strip():
            raise InvalidLinkedInUrlError(
                "LinkedIn profile URL is required"
            )

        value = url.strip()
        parsed = urlparse(value)

        if parsed.scheme not in {"http", "https"}:
            raise InvalidLinkedInUrlError(
                "LinkedIn profile URL must use http or https"
            )

        hostname = (parsed.hostname or "").lower()

        if hostname not in {
            "linkedin.com",
            "www.linkedin.com",
        }:
            raise InvalidLinkedInUrlError(
                "LinkedIn profile URL must point to linkedin.com"
            )

        if not re.search(
            r"/in/[A-Za-z0-9\-_%]+/?$",
            parsed.path,
            flags=re.IGNORECASE,
        ):
            raise InvalidLinkedInUrlError(
                "LinkedIn profile URL must target a /in/ profile"
            )

        return value
