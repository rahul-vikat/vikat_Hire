from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from vikat_hire.app.api import create_app
from vikat_hire.app.composition import create_production_app
from vikat_hire.app.settings import ApplicationSettings
from vikat_hire.collection.github import GitHubCollector
from vikat_hire.collection.linkedin import LinkedInCollector
from vikat_hire.collection.portfolio import PortfolioCollector
from vikat_hire.config.jd_classification import JDClassificationConfiguration
from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.explanation import ExplanationResult
from vikat_hire.normalization.document import extract_document_text
from vikat_hire.orchestration.graph import (
    ScreeningGraphDependencies,
    build_screening_graph,
)
from vikat_hire.orchestration.state import from_orchestration_state
from vikat_hire.persistence.postgres import PostgresScreeningIdRegistry

pytestmark = pytest.mark.skipif(
    not os.environ.get("VIKATHIRE_TEST_DATABASE_URL"),
    reason="set VIKATHIRE_TEST_DATABASE_URL to run PostgreSQL integration tests",
)


class _Fetcher:
    def fetch(self, *, url: str) -> str:
        raise AssertionError("no external URL is configured in this test")


def _pool() -> ConnectionPool:
    pool = ConnectionPool(
        conninfo=os.environ["VIKATHIRE_TEST_DATABASE_URL"],
        min_size=1,
        max_size=4,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        open=True,
    )
    return pool


def _graph(checkpointer: PostgresSaver):
    return build_screening_graph(
        dependencies=ScreeningGraphDependencies(
            classification_configuration=JDClassificationConfiguration(
                configuration_ref="postgres-test-classification@1",
                technical_indicators=("python",),
                non_technical_indicators=("communications role",),
            ),
            linkedin_collector=LinkedInCollector(_Fetcher()),
            github_collector=GitHubCollector(_Fetcher()),
            portfolio_collector=PortfolioCollector(_Fetcher()),
            scoring_release="verifyhire-scoring@2.2.0",
            policy_field_presence={
                "certification": True,
                "education": True,
                "location": True,
                "availability": True,
            },
            policy_configuration_ref="postgres-test-policy@1",
            explanation_generator=lambda context: ExplanationResult(
                screening_id=context.screening_id,
                summary="PostgreSQL restart test.",
                dimensions=(),
                generated_by="test",
                evidence_refs=(),
            ),
        ),
        checkpointer=checkpointer,
    )


def _submission(screening_id: str) -> dict:
    return {
        "screening_input": {
            "screening_id": screening_id,
            "jd": {
                "input_id": f"{screening_id}-jd",
                "kind": "jd",
                "filename": "jd.txt",
                "media_type": "text/plain",
                "content_hash": "jd-hash",
                "storage_ref": "opaque/jd",
            },
            "resume": {
                "input_id": f"{screening_id}-resume",
                "kind": "resume",
                "filename": "resume.txt",
                "media_type": "text/plain",
                "content_hash": "resume-hash",
                "storage_ref": "opaque/resume",
            },
        }
    }


def test_postgres_checkpoint_survives_application_restart_and_resumes() -> None:
    screening_id = f"restart-{uuid4()}"
    pool1 = _pool()
    saver1 = PostgresSaver(pool1)
    saver1.setup()
    graph1 = _graph(saver1)
    client1 = TestClient(create_app(graph=graph1))

    interrupted = client1.post("/screenings", json=_submission(screening_id))
    assert interrupted.status_code == 202, interrupted.text
    client1.close()
    pool1.close()

    pool2 = _pool()
    saver2 = PostgresSaver(pool2)
    saver2.setup()
    graph2 = _graph(saver2)
    client2 = TestClient(create_app(graph=graph2))
    try:
        current = client2.get(f"/screenings/{screening_id}")
        assert current.status_code == 200, current.text
        assert current.json()["interruption"] is not None

        snapshot = graph2.get_state({"configurable": {"thread_id": screening_id}})
        state, _, _ = from_orchestration_state(snapshot.values)
        jd_provenance = next(
            item.provenance_id
            for item in state.provenances
            if item.source_type is SourceType.JD_FILE
        )
        resume_provenance = next(
            item.provenance_id
            for item in state.provenances
            if item.source_type is SourceType.RESUME_FILE
        )
        blocks = (
            *extract_document_text(
                document=state.screening_input.jd,
                content=b"Must have: Python\nOwn services end-to-end.",
                provenance_refs=(jd_provenance,),
            ),
            *extract_document_text(
                document=state.screening_input.resume,
                content=b"Python developer\nOwned services end-to-end.",
                provenance_refs=(resume_provenance,),
            ),
        )
        resumed = client2.post(
            f"/screenings/{screening_id}/resume",
            json={
                "screening_input": state.screening_input.model_dump(mode="json"),
                "extracted_blocks": [block.model_dump(mode="json") for block in blocks],
            },
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["report"]["score"] is not None
    finally:
        client2.close()
        saver2.delete_thread(screening_id)
        pool2.close()


def test_postgres_registry_atomically_reserves_duplicate_screening_ids() -> None:
    pool = _pool()
    registry = PostgresScreeningIdRegistry(pool)
    registry.setup()
    screening_id = f"unique-{uuid4()}"
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(lambda _: registry.reserve(screening_id), range(2)))
        assert sorted(results) == [False, True]
    finally:
        registry.release_if_unstarted(screening_id)
        pool.close()


def test_production_composition_starts_with_postgres_checkpointer() -> None:
    settings = ApplicationSettings(
        _env_file=None,
        VIKATHIRE_APP_NAME="VikatHire PostgreSQL integration",
        VIKATHIRE_ENVIRONMENT="test",
        VIKATHIRE_LOG_LEVEL="INFO",
        VIKATHIRE_DATABASE_URL=os.environ["VIKATHIRE_TEST_DATABASE_URL"],
        VIKATHIRE_APIFY_API_TOKEN="apify-test-secret",
        VIKATHIRE_APIFY_LINKEDIN_ACTOR_ID="test-actor",
        VIKATHIRE_GROQ_API_KEY="groq-test-secret",
        VIKATHIRE_GROQ_MODEL="test-model",
        VIKATHIRE_JD_TECHNICAL_INDICATORS="python, api",
        VIKATHIRE_JD_NON_TECHNICAL_INDICATORS="recruiting, communications",
        VIKATHIRE_JD_CLASSIFICATION_CONFIGURATION_REF="integration-classification@1",
        VIKATHIRE_POLICY_CONFIGURATION_REF="integration-policy@1",
        VIKATHIRE_POLICY_CERTIFICATION_PRESENT=True,
        VIKATHIRE_POLICY_EDUCATION_PRESENT=True,
        VIKATHIRE_POLICY_LOCATION_PRESENT=True,
        VIKATHIRE_POLICY_AVAILABILITY_PRESENT=True,
    )
    app = create_production_app(settings=settings)

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/readiness").json() == {"status": "ready"}
        assert app.title == "VikatHire PostgreSQL integration"
        assert getattr(app.state.screening_graph, "checkpointer", None) is not None
