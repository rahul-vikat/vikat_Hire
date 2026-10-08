from __future__ import annotations

import json

import httpx
import pytest

from vikat_hire.collection.apify_linkedin import (
    ApifyActorExecutionError,
    ApifyAuthenticationError,
    ApifyConfigurationError,
    ApifyLinkedInFetcher,
    ApifyMalformedResponseError,
    InvalidLinkedInUrlError,
)


class FakeApifyTransport(httpx.BaseTransport):
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = iter(responses)
        self.requests: list[httpx.Request] = []

    def handle_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        self.requests.append(request)

        response = next(self._responses)
        response.request = request

        return response


def _response(
    *,
    status_code: int,
    json_body: object,
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_body,
    )


def test_fetch_runs_actor_polls_run_and_reads_dataset() -> None:
    transport = FakeApifyTransport(
        [
            _response(
                status_code=201,
                json_body={
                    "data": {
                        "id": "run-123",
                        "status": "RUNNING",
                        "defaultDatasetId": "dataset-123",
                    },
                },
            ),
            _response(
                status_code=200,
                json_body={
                    "data": {
                        "id": "run-123",
                        "status": "SUCCEEDED",
                        "defaultDatasetId": "dataset-123",
                    },
                },
            ),
            _response(
                status_code=200,
                json_body=[
                    {
                        "name": "Jane Doe",
                        "skills": ["Python", "FastAPI"],
                    },
                ],
            ),
        ],
    )

    fetcher = ApifyLinkedInFetcher(
        api_token="test-token",
        actor_id="example/linkedin-actor",
        poll_interval_seconds=0,
        transport=transport,
    )

    result = fetcher.fetch(
        url="https://www.linkedin.com/in/jane-doe",
    )

    assert json.loads(result) == [
        {
            "name": "Jane Doe",
            "skills": ["Python", "FastAPI"],
        },
    ]

    assert len(transport.requests) == 3

    start_request = transport.requests[0]

    assert start_request.method == "POST"
    assert start_request.url.path == (
        "/v2/acts/example/linkedin-actor/runs"
    )
    assert start_request.headers["Authorization"] == "Bearer test-token"

    body = json.loads(start_request.content)

    assert body == {
        "startUrls": [
            {
                "url": "https://www.linkedin.com/in/jane-doe",
            },
        ],
    }

    assert transport.requests[1].url.path == (
        "/v2/actor-runs/run-123"
    )

    assert transport.requests[2].url.path == (
        "/v2/datasets/dataset-123/items"
    )


def test_fetch_produces_deterministic_json() -> None:
    def run() -> str:
        transport = FakeApifyTransport(
            [
                _response(
                    status_code=201,
                    json_body={
                        "data": {
                            "id": "run-123",
                            "status": "SUCCEEDED",
                            "defaultDatasetId": "dataset-123",
                        },
                    },
                ),
                _response(
                    status_code=200,
                    json_body=[
                        {
                            "z": "last",
                            "a": "first",
                        },
                    ],
                ),
            ],
        )

        return ApifyLinkedInFetcher(
            api_token="test-token",
            actor_id="example/linkedin-actor",
            poll_interval_seconds=0,
            transport=transport,
        ).fetch(
            url="https://www.linkedin.com/in/jane-doe",
        )

    assert run() == run()


def test_accepts_dataset_items_object_response() -> None:
    transport = FakeApifyTransport(
        [
            _response(
                status_code=201,
                json_body={
                    "data": {
                        "id": "run-123",
                        "status": "SUCCEEDED",
                        "defaultDatasetId": "dataset-123",
                    },
                },
            ),
            _response(
                status_code=200,
                json_body={
                    "items": [
                        {
                            "name": "Jane Doe",
                        },
                    ],
                },
            ),
        ],
    )

    result = ApifyLinkedInFetcher(
        api_token="test-token",
        actor_id="example/linkedin-actor",
        poll_interval_seconds=0,
        transport=transport,
    ).fetch(
        url="https://linkedin.com/in/jane-doe",
    )

    assert json.loads(result) == [
        {
            "name": "Jane Doe",
        },
    ]


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "https://example.com/in/jane-doe",
        "https://www.linkedin.com/company/example",
        "https://www.linkedin.com/in/",
        "ftp://www.linkedin.com/in/jane-doe",
    ],
)
def test_rejects_invalid_linkedin_profile_url(url: str) -> None:
    fetcher = ApifyLinkedInFetcher(
        api_token="test-token",
        actor_id="example/linkedin-actor",
    )

    with pytest.raises(InvalidLinkedInUrlError):
        fetcher.fetch(url=url)


def test_requires_apify_token() -> None:
    with pytest.raises(
        ApifyConfigurationError,
        match="API token",
    ):
        ApifyLinkedInFetcher(
            api_token=" ",
            actor_id="example/linkedin-actor",
        )


def test_requires_actor_id() -> None:
    with pytest.raises(
        ApifyConfigurationError,
        match="actor ID",
    ):
        ApifyLinkedInFetcher(
            api_token="test-token",
            actor_id=" ",
        )


def test_maps_authentication_failure() -> None:
    transport = FakeApifyTransport(
        [
            _response(
                status_code=401,
                json_body={"error": "unauthorized"},
            ),
        ],
    )

    fetcher = ApifyLinkedInFetcher(
        api_token="bad-token",
        actor_id="example/linkedin-actor",
        transport=transport,
    )

    with pytest.raises(ApifyAuthenticationError):
        fetcher.fetch(
            url="https://www.linkedin.com/in/jane-doe",
        )


def test_maps_actor_failure() -> None:
    transport = FakeApifyTransport(
        [
            _response(
                status_code=201,
                json_body={
                    "data": {
                        "id": "run-123",
                        "status": "FAILED",
                    },
                },
            ),
        ],
    )

    fetcher = ApifyLinkedInFetcher(
        api_token="test-token",
        actor_id="example/linkedin-actor",
        transport=transport,
    )

    with pytest.raises(ApifyActorExecutionError):
        fetcher.fetch(
            url="https://www.linkedin.com/in/jane-doe",
        )


def test_rejects_missing_run_id() -> None:
    transport = FakeApifyTransport(
        [
            _response(
                status_code=201,
                json_body={
                    "data": {
                        "status": "RUNNING",
                    },
                },
            ),
        ],
    )

    fetcher = ApifyLinkedInFetcher(
        api_token="test-token",
        actor_id="example/linkedin-actor",
        transport=transport,
    )

    with pytest.raises(ApifyMalformedResponseError):
        fetcher.fetch(
            url="https://www.linkedin.com/in/jane-doe",
        )


def test_rejects_empty_dataset() -> None:
    transport = FakeApifyTransport(
        [
            _response(
                status_code=201,
                json_body={
                    "data": {
                        "id": "run-123",
                        "status": "SUCCEEDED",
                        "defaultDatasetId": "dataset-123",
                    },
                },
            ),
            _response(
                status_code=200,
                json_body=[],
            ),
        ],
    )

    fetcher = ApifyLinkedInFetcher(
        api_token="test-token",
        actor_id="example/linkedin-actor",
        poll_interval_seconds=0,
        transport=transport,
    )

    with pytest.raises(
        ApifyMalformedResponseError,
        match="no profile items",
    ):
        fetcher.fetch(
            url="https://www.linkedin.com/in/jane-doe",
        )
