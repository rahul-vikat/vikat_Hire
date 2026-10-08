from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from vikat_hire.app.api import create_app
from vikat_hire.app.dependencies import ApplicationDependencyError
from vikat_hire.collection.github import GitHubCollector
from vikat_hire.collection.linkedin import LinkedInCollector
from vikat_hire.collection.portfolio import PortfolioCollector
from vikat_hire.config.jd_classification import JDClassificationConfiguration
from vikat_hire.contracts.common import (
    SourceType,
)
from vikat_hire.contracts.explanation import ExplanationResult
from vikat_hire.normalization.document import extract_document_text
from vikat_hire.orchestration.graph import (
    ScreeningGraphDependencies,
    build_screening_graph,
)
from vikat_hire.orchestration.state import from_orchestration_state
from vikat_hire.presentation.report import ScreeningReport


class _Fetcher:
    def fetch(self, *, url: str) -> str:
        return ""


def _graph(*, fail_location_gate: bool = False):
    field_presence = {
        "certification": True,
        "education": True,
        "location": not fail_location_gate,
        "availability": True,
    }
    return build_screening_graph(
        dependencies=ScreeningGraphDependencies(
            classification_configuration=JDClassificationConfiguration(
                configuration_ref="jd-classification-test@1",
                technical_indicators=("python",),
                non_technical_indicators=("communications role",),
            ),
            linkedin_collector=LinkedInCollector(_Fetcher()),
            github_collector=GitHubCollector(_Fetcher()),
            portfolio_collector=PortfolioCollector(_Fetcher()),
            scoring_release="verifyhire-scoring@2.2.0",
            policy_field_presence=field_presence,
            policy_configuration_ref="policy-test@1",
            explanation_generator=lambda context: ExplanationResult(
                screening_id=context.screening_id,
                summary="Test explanation.",
                dimensions=(),
                generated_by="test",
                evidence_refs=(),
            ),
        ),
        checkpointer=MemorySaver(),
    )


def _payload(screening_id: str = "api-screening-1") -> dict:
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


def _content(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def test_post_screening_returns_authoritative_completed_report() -> None:
    client = TestClient(create_app(graph=_graph()))
    payload = _payload()
    payload.update(
        {
            "jd_content": _content("Must have: Python\nOwn services end-to-end."),
            "resume_content": _content("Python developer\nOwned services end-to-end."),
        }
    )

    response = client.post("/screenings", json=payload)

    assert response.status_code == 200, response.text
    result = response.json()
    report = ScreeningReport.model_validate(result["report"])
    assert report.screening_id == "api-screening-1"
    assert report.evaluation is not None
    assert report.score is not None
    assert report.policy is not None
    assert report.explanation is not None
    assert "interruption" not in result or result["interruption"] is None


def test_missing_document_bytes_interrupt_and_resume() -> None:
    graph = _graph()
    client = TestClient(create_app(graph=graph))
    payload = _payload("api-resume-1")

    response = client.post("/screenings", json=payload)

    assert response.status_code == 202
    interruption = response.json()["interruption"]
    assert set(interruption["required_inputs_missing"]) == {
        "jd.extracted_content",
        "resume.extracted_content",
    }

    snapshot = graph.get_state({"configurable": {"thread_id": "api-resume-1"}})
    state, _, _ = from_orchestration_state(snapshot.values)
    jd_ref = next(
        provenance.provenance_id
        for provenance in state.provenances
        if provenance.source_type is SourceType.JD_FILE
    )
    resume_ref = next(
        provenance.provenance_id
        for provenance in state.provenances
        if provenance.source_type is SourceType.RESUME_FILE
    )
    jd_blocks = extract_document_text(
        document=state.screening_input.jd,
        content=b"Must have: Python\nOwn services end-to-end.",
        provenance_refs=(jd_ref,),
    )
    resume_blocks = extract_document_text(
        document=state.screening_input.resume,
        content=b"Python developer\nOwned services end-to-end.",
        provenance_refs=(resume_ref,),
    )
    resume_payload = {
        "screening_input": state.screening_input.model_dump(mode="json"),
        "extracted_blocks": [
            block.model_dump(mode="json") for block in (*jd_blocks, *resume_blocks)
        ],
    }

    resumed = client.post(
        "/screenings/api-resume-1/resume",
        json=resume_payload,
    )

    assert resumed.status_code == 200, resumed.text
    resumed_report = ScreeningReport.model_validate(resumed.json()["report"])
    assert resumed_report.screening_id == "api-resume-1"
    assert resumed_report.score is not None
    assert resumed_report.policy is not None


def test_api_returns_failed_policy_without_recalculating_result() -> None:
    client = TestClient(create_app(graph=_graph(fail_location_gate=True)))
    payload = _payload("api-failed-policy")
    payload.update(
        {
            "jd_content": _content("Must have: Python\nOwn services end-to-end."),
            "resume_content": _content("Python developer\nOwned services end-to-end."),
        }
    )

    response = client.post("/screenings", json=payload)

    assert response.status_code == 200
    report = ScreeningReport.model_validate(response.json()["report"])
    assert report.score is not None
    assert report.policy is not None
    assert report.policy.workflow_status.value == "failed"
    assert report.policy.suitability_eligible is False


def test_api_preserves_review_required_policy_result() -> None:
    client = TestClient(create_app(graph=_graph()))
    payload = _payload("api-review")
    payload.update(
        {
            "jd_content": _content(
                "Must have: Python\nOwn services end-to-end.\nNo ownership of services end-to-end."
            ),
            "resume_content": _content("Python developer\nOwned services end-to-end."),
        }
    )

    response = client.post("/screenings", json=payload)

    assert response.status_code == 200
    report = ScreeningReport.model_validate(response.json()["report"])
    assert report.policy is not None
    assert report.policy.workflow_status.value == "review_required"
    assert report.review_requests


def test_resume_rejects_screening_identity_mismatch() -> None:
    client = TestClient(create_app(graph=_graph()))
    response = client.post(
        "/screenings/not-the-payload-id/resume",
        json={
            "screening_input": _payload("payload-id")["screening_input"],
            "extracted_blocks": [],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == ("resume screening_id does not match requested screening")


def test_invalid_screening_request_uses_typed_validation_response() -> None:
    client = TestClient(create_app(graph=_graph()))

    response = client.post("/screenings", json={"screening_input": {}})

    assert response.status_code == 422
    assert response.json()["detail"]


def test_blank_screening_id_is_rejected_as_client_input() -> None:
    client = TestClient(create_app(graph=_graph()))
    payload = _payload(" ")
    payload.update(
        {
            "jd_content": _content("JD text"),
            "resume_content": _content("Resume text"),
        }
    )

    response = client.post("/screenings", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == "screening_id must not be blank"


def test_get_returns_not_found_for_unknown_screening() -> None:
    client = TestClient(create_app(graph=_graph()))

    response = client.get("/screenings/unknown-screening")

    assert response.status_code == 404


def test_health_and_readiness_are_available_without_provider_calls() -> None:
    client = TestClient(create_app(graph=_graph()))

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/readiness").json() == {"status": "ready"}


def test_request_body_limit_returns_413_without_truncating() -> None:
    client = TestClient(create_app(graph=_graph(), max_request_bytes=32))

    response = client.post("/screenings", content=b"x" * 33)

    assert response.status_code == 413
    assert response.json() == {"detail": "request body exceeds configured size limit"}


def test_app_requires_checkpointed_graph() -> None:
    class UncheckpointedGraph:
        def invoke(self, input, config):
            raise AssertionError("not invoked")

        def get_state(self, config):
            raise AssertionError("not invoked")

    with pytest.raises(
        ApplicationDependencyError,
        match="injected LangGraph checkpointer",
    ):
        create_app(graph=UncheckpointedGraph())


def test_duplicate_screening_id_returns_conflict() -> None:
    client = TestClient(create_app(graph=_graph()))
    payload = _payload("api-duplicate")

    first = client.post("/screenings", json=payload)
    second = client.post("/screenings", json=payload)

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["detail"] == "screening_id already exists"


def test_registry_does_not_overwrite_checkpoint_created_before_registry() -> None:
    class ExistingGraph:
        checkpointer = object()

        def invoke(self, input, config):
            raise AssertionError("existing checkpoint must not be overwritten")

        def get_state(self, config):
            return type("Snapshot", (), {"values": {"screening_state": {}}})()

    class Registry:
        reserved_ids: list[str] = []

        def reserve(self, screening_id: str) -> bool:
            self.reserved_ids.append(screening_id)
            return True

        def release_if_unstarted(self, screening_id: str) -> None:
            raise AssertionError("existing checkpoint reservation must be retained")

    app = create_app(graph=ExistingGraph())
    registry = Registry()
    app.state.screening_id_registry = registry
    client = TestClient(app)

    response = client.post("/screenings", json=_payload("legacy-checkpoint"))

    assert response.status_code == 409
    assert registry.reserved_ids == ["legacy-checkpoint"]


def test_unexpected_graph_error_has_safe_http_response() -> None:
    class BrokenGraph:
        checkpointer = object()

        def invoke(self, input, config):
            raise RuntimeError("private provider failure details")

        def get_state(self, config):
            return type("EmptySnapshot", (), {"values": {}})()

    client = TestClient(
        create_app(graph=BrokenGraph()),
        raise_server_exceptions=False,
    )
    payload = _payload("api-provider-failure")
    payload.update(
        {
            "jd_content": _content("JD text"),
            "resume_content": _content("Resume text"),
        }
    )

    response = client.post("/screenings", json=payload)

    assert response.status_code == 500
    assert response.json() == {"detail": "internal screening service error"}
    assert "private provider failure details" not in response.text
