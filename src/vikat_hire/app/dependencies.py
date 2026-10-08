from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from fastapi import Request
from pydantic import Base64Bytes

from vikat_hire.collection.apify_linkedin import ApifyLinkedInFetcher
from vikat_hire.collection.collector import build_collection_result
from vikat_hire.collection.github import GitHubCollector, GitHubFetcher
from vikat_hire.collection.linkedin import LinkedInCollector
from vikat_hire.collection.portfolio import PortfolioCollector, PortfolioFetcher
from vikat_hire.collection.registry import ExternalCollectorRegistry
from vikat_hire.contracts.common import ContractModel, InputKind, SourceType
from vikat_hire.contracts.inputs import ScreeningInput
from vikat_hire.contracts.state import ScreeningState
from vikat_hire.orchestration.state import from_orchestration_state
from vikat_hire.presentation.report import ScreeningReport, build_screening_report


class ApplicationDependencyError(ValueError):
    """Raised when application dependency construction is invalid."""


class ScreeningGraphPort(Protocol):
    """The graph operations required by the HTTP boundary."""

    def invoke(self, input: Mapping[str, Any], config: Mapping[str, Any]) -> Any: ...

    def get_state(self, config: Mapping[str, Any]) -> Any: ...


class ScreeningSubmission(ContractModel):
    """HTTP payload; document bytes are base64 transport, not domain state."""

    screening_input: ScreeningInput
    jd_content: Base64Bytes | None = None
    resume_content: Base64Bytes | None = None


class InputInterruptionSummary(ContractModel):
    screening_id: str
    current_node: str
    required_inputs_missing: tuple[str, ...]
    revision: int


class ScreeningAPIResponse(ContractModel):
    report: ScreeningReport
    interruption: InputInterruptionSummary | None = None


def report_from_graph_values(values: Any) -> ScreeningAPIResponse:
    """Validate graph values and project their authoritative report."""
    if not isinstance(values, Mapping):
        raise ApplicationDependencyError("graph state values must be a mapping")
    transport = {
        key: values[key]
        for key in ("screening_state", "extracted_blocks", "normalization")
        if key in values
    }
    state, _, _ = from_orchestration_state(transport)
    interruption = None
    if state.required_inputs_missing:
        interruption = InputInterruptionSummary(
            screening_id=state.screening_id,
            current_node=state.current_node,
            required_inputs_missing=state.required_inputs_missing,
            revision=state.revision,
        )
    return ScreeningAPIResponse(
        report=build_screening_report(state),
        interruption=interruption,
    )


def provide_screening_graph(request: Request) -> ScreeningGraphPort:
    graph = getattr(request.app.state, "screening_graph", None)
    if not callable(getattr(graph, "invoke", None)) or not callable(
        getattr(graph, "get_state", None)
    ):
        raise ApplicationDependencyError(
            "application requires an injected compiled screening graph"
        )
    return graph


def build_initial_screening_state(
    screening_input: ScreeningInput,
) -> ScreeningState:
    """Build initial domain state and provenance from typed input metadata."""
    if not isinstance(screening_input, ScreeningInput):
        raise ApplicationDependencyError("screening_input must be a ScreeningInput")
    if not screening_input.screening_id.strip():
        raise ApplicationDependencyError("screening_id must not be blank")
    if screening_input.jd.kind is not InputKind.JD:
        raise ApplicationDependencyError("jd document kind must be 'jd'")
    if screening_input.resume.kind is not InputKind.RESUME:
        raise ApplicationDependencyError("resume document kind must be 'resume'")

    collection = build_collection_result(screening_input=screening_input)
    return ScreeningState(
        screening_id=screening_input.screening_id,
        screening_input=screening_input,
        provenances=collection.provenances,
    )


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
        raise ApplicationDependencyError("Apify API token must be a non-empty string")

    if not isinstance(apify_actor_id, str) or not apify_actor_id.strip():
        raise ApplicationDependencyError("Apify actor ID must be a non-empty string")

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
        raise ApplicationDependencyError("LinkedIn fetcher must provide fetch()")

    if not callable(getattr(github_fetcher, "fetch", None)):
        raise ApplicationDependencyError("GitHub fetcher must provide fetch()")

    if not callable(getattr(portfolio_fetcher, "fetch", None)):
        raise ApplicationDependencyError("Portfolio fetcher must provide fetch()")

    return ExternalCollectorRegistry(
        {
            SourceType.LINKEDIN: LinkedInCollector(linkedin_fetcher),
            SourceType.GITHUB: GitHubCollector(github_fetcher),
            SourceType.PORTFOLIO: PortfolioCollector(portfolio_fetcher),
        }
    )
