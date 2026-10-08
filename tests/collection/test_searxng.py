from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from vikat_hire.collection.searxng import (
    SearXNGClient,
    SearXNGConfiguration,
    SearXNGMalformedResponseError,
    SearXNGUnavailableError,
)
from vikat_hire.config.research_queries import (
    RESEARCH_QUERY_DEFINITIONS,
    get_research_query,
)
from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.research import ResearchDimension, ResearchEntityType


def test_fixed_company_and_college_queries_are_exact() -> None:
    expected = (
        (ResearchEntityType.COMPANY, ResearchDimension.FINANCIAL_VALUATION,
         '"VIKAT.AI" funding valuation revenue investors'),
        (ResearchEntityType.COMPANY, ResearchDimension.MARKET_POSITION,
         '"VIKAT.AI" customers products competitors market'),
        (ResearchEntityType.COMPANY, ResearchDimension.ENGINEERING_TECHNICAL,
         '"VIKAT.AI" engineering technology AI patents research'),
        (ResearchEntityType.COMPANY, ResearchDimension.REPUTATION_COMPLIANCE,
         '"VIKAT.AI" certifications compliance security reputation'),
        (ResearchEntityType.COLLEGE, ResearchDimension.OFFICIAL_RANKING,
         '"IIT Patna" NIRF ranking QS THE ranking'),
        (ResearchEntityType.COLLEGE, ResearchDimension.ACCREDITATION,
         '"IIT Patna" NAAC NBA UGC AICTE accreditation recognition'),
        (ResearchEntityType.COLLEGE, ResearchDimension.ACADEMIC_RESEARCH,
         '"IIT Patna" research publications citations patents faculty'),
        (ResearchEntityType.COLLEGE, ResearchDimension.PLACEMENTS,
         '"IIT Patna" placement report median salary recruiters placement'),
        (ResearchEntityType.COLLEGE, ResearchDimension.PERCEPTION_INFRASTRUCTURE,
         '"IIT Patna" alumni campus infrastructure student life'),
    )

    assert len(RESEARCH_QUERY_DEFINITIONS) == 9
    assert tuple(
        get_research_query(
            entity_type=entity_type,
            dimension=dimension,
            entity_name=(
                "VIKAT.AI"
                if entity_type is ResearchEntityType.COMPANY
                else "IIT Patna"
            ),
        )
        for entity_type, dimension, _ in expected
    ) == tuple(query for _, _, query in expected)


def test_query_rejects_blank_entity_name() -> None:
    with pytest.raises(ValueError, match="entity_name must not be blank"):
        get_research_query(
            entity_type=ResearchEntityType.COMPANY,
            dimension=ResearchDimension.MARKET_POSITION,
            entity_name=" ",
        )


def _client(
    transport: httpx.BaseTransport | None = None,
    *,
    max_results: int = 20,
) -> SearXNGClient:
    return SearXNGClient(
        SearXNGConfiguration(
            base_url="http://localhost:8080",
            max_results=max_results,
        ),
        transport=transport,
    )


def test_configuration_loads_existing_environment_setting_names() -> None:
    configuration = SearXNGConfiguration.from_environment(
        {
            "SEARXNG_BASE_URL": "http://localhost:8080",
            "VIKATHIRE_SEARXNG_TIMEOUT_SECONDS": "15.0",
            "VIKATHIRE_SEARXNG_MAX_RESULTS": "20",
        }
    )

    assert configuration.search_url == "http://localhost:8080/search"
    assert configuration.timeout_seconds == 15.0
    assert configuration.max_results == 20


def test_configuration_rejects_missing_environment_settings() -> None:
    with pytest.raises(ValueError, match="missing SearXNG environment"):
        SearXNGConfiguration.from_environment({})


def test_search_requests_exact_parameters_and_collects_raw_results() -> None:
    seen: list[httpx.Request] = []
    query = '"VIKAT.AI" funding valuation revenue investors'

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "query": query,
                "results": [
                    {
                        "title": "Vikat AI company page",
                        "url": "https://example.test/vikat",
                        "content": "Organization facts from source.",
                    }
                ],
            },
        )

    batch = _client(httpx.MockTransport(handler)).search(
        entity_type=ResearchEntityType.COMPANY,
        entity_name="VIKAT.AI",
        dimension=ResearchDimension.FINANCIAL_VALUATION,
    )

    assert len(seen) == 1
    assert urlsplit(str(seen[0].url)).path == "/search"
    assert parse_qs(seen[0].url.query.decode()) == {
        "q": [query],
        "format": ["json"],
        "language": ["en"],
        "categories": ["general"],
    }
    assert len(batch.results) == 1
    assert batch.results[0].title == "Vikat AI company page"
    assert batch.results[0].content == "Organization facts from source."
    assert batch.results[0].dimension is ResearchDimension.FINANCIAL_VALUATION
    assert batch.provenances[0].source_type is SourceType.SEARXNG
    assert batch.provenances[0].source_uri == "https://example.test/vikat"
    assert batch.provenances[0].locator == {
        "entity_type": "company",
        "entity_name": "VIKAT.AI",
        "dimension": "financial_valuation",
        "query": query,
        "result_index": "0",
    }
    assert batch.results[0].provenance_refs == (
        batch.provenances[0].provenance_id,
    )


def test_result_ids_are_deterministic_and_duplicate_results_are_preserved() -> None:
    client = _client()
    query = '"IIT Patna" NAAC NBA UGC AICTE accreditation recognition'
    payload = {
        "query": query,
        "results": [
            {"title": "same", "url": "https://example.test", "content": "same"},
            {"title": "same", "url": "https://example.test", "content": "same"},
        ],
    }
    kwargs = {
        "entity_type": ResearchEntityType.COLLEGE,
        "entity_name": "IIT Patna",
        "dimension": ResearchDimension.ACCREDITATION,
        "requested_query": query,
    }

    first = client.parse_response(payload, **kwargs)
    second = client.parse_response(payload, **kwargs)

    assert len(first.results) == 2
    assert first.results[0].result_id != first.results[1].result_id
    assert [item.result_id for item in first.results] == [
        item.result_id for item in second.results
    ]
    assert [item.provenance_refs for item in first.results] == [
        item.provenance_refs for item in second.results
    ]


def test_result_limit_is_applied_without_changing_result_order() -> None:
    query = '"VIKAT.AI" customers products competitors market'
    payload = {
        "query": query,
        "results": [
            {"title": str(index), "url": f"https://example.test/{index}", "content": "x"}
            for index in range(3)
        ],
    }

    batch = _client(max_results=2).parse_response(
        payload,
        entity_type=ResearchEntityType.COMPANY,
        entity_name="VIKAT.AI",
        dimension=ResearchDimension.MARKET_POSITION,
        requested_query=query,
    )

    assert [item.title for item in batch.results] == ["0", "1"]


def test_empty_results_are_explicitly_returned_as_empty_batch() -> None:
    query = '"IIT Patna" research publications citations patents faculty'
    batch = _client().parse_response(
        {"query": query, "results": []},
        entity_type=ResearchEntityType.COLLEGE,
        entity_name="IIT Patna",
        dimension=ResearchDimension.ACADEMIC_RESEARCH,
        requested_query=query,
    )

    assert batch.results == ()
    assert batch.provenances == ()


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "must be a JSON object"),
        ({"results": []}, "response query"),
        ({"query": "wrong", "results": []}, "does not match"),
        ({"query": "q", "results": {}}, "results must be a list"),
        ({"query": "q", "results": [None]}, r"results\[0\] must be an object"),
        (
            {"query": "q", "results": [{"title": "t", "url": "u"}]},
            "must be strings",
        ),
    ],
)
def test_malformed_response_fails_explicitly(payload, message: str) -> None:
    with pytest.raises(SearXNGMalformedResponseError, match=message):
        _client().parse_response(
            payload,
            entity_type=ResearchEntityType.COMPANY,
            entity_name="VIKAT.AI",
            dimension=ResearchDimension.MARKET_POSITION,
            requested_query="q",
        )


def test_unavailable_searxng_is_reported() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(SearXNGUnavailableError, match="request failed"):
        _client(httpx.MockTransport(handler)).search(
            entity_type=ResearchEntityType.COMPANY,
            entity_name="VIKAT.AI",
            dimension=ResearchDimension.MARKET_POSITION,
        )


def test_invalid_json_is_reported_as_malformed_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    with pytest.raises(SearXNGMalformedResponseError, match="not valid JSON"):
        _client(httpx.MockTransport(handler)).search(
            entity_type=ResearchEntityType.COMPANY,
            entity_name="VIKAT.AI",
            dimension=ResearchDimension.MARKET_POSITION,
        )


def test_search_endpoint_preserves_existing_search_path() -> None:
    assert SearXNGConfiguration(
        "http://localhost:8080/search"
    ).search_url == "http://localhost:8080/search"
