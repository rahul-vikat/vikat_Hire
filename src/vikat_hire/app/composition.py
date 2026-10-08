from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from groq import Groq
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from vikat_hire.ai.groq_controller import GroqController
from vikat_hire.app.api import create_app
from vikat_hire.app.dependencies import ApplicationDependencyError, build_linkedin_fetcher
from vikat_hire.app.settings import ApplicationSettings
from vikat_hire.collection.github import GitHubCollector
from vikat_hire.collection.http_providers import (
    GitHubAPITextFetcher,
    HTTPPortfolioTextFetcher,
)
from vikat_hire.collection.linkedin import LinkedInCollector
from vikat_hire.collection.portfolio import PortfolioCollector
from vikat_hire.config.jd_classification import JDClassificationConfiguration
from vikat_hire.config.models import AIModelConfiguration, AIRuntimeConfiguration
from vikat_hire.config.scoring_2_2_0 import SCORING_RELEASE_2_2_0
from vikat_hire.orchestration.graph import (
    ScreeningGraphDependencies,
    build_screening_graph,
)
from vikat_hire.persistence.postgres import PostgresScreeningIdRegistry


def create_production_app(
    *,
    settings: ApplicationSettings | None = None,
):
    """Create the FastAPI application; open durable resources in lifespan."""
    runtime: dict[str, ApplicationSettings] = {}

    @asynccontextmanager
    async def lifespan(app) -> AsyncIterator[None]:
        runtime_settings = settings or ApplicationSettings()
        runtime["settings"] = runtime_settings
        logging.basicConfig(level=runtime_settings.log_level)
        pool = ConnectionPool(
            conninfo=runtime_settings.psycopg_conninfo,
            min_size=runtime_settings.postgres_pool_min_size,
            max_size=runtime_settings.postgres_pool_max_size,
            timeout=float(runtime_settings.network_timeout_seconds),
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            open=False,
        )
        groq_client: Groq | None = None
        try:
            pool.open(wait=True)
            checkpointer = PostgresSaver(pool)
            checkpointer.setup()
            screening_registry = PostgresScreeningIdRegistry(pool)
            screening_registry.setup()

            linked_in_fetcher = build_linkedin_fetcher(
                apify_api_token=runtime_settings.apify_api_token.get_secret_value(),
                apify_actor_id=runtime_settings.apify_linkedin_actor_id,
                timeout_seconds=float(runtime_settings.apify_timeout_seconds),
                poll_interval_seconds=float(runtime_settings.apify_poll_interval_seconds),
            )
            github_fetcher = GitHubAPITextFetcher(
                token=(
                    runtime_settings.github_api_token.get_secret_value()
                    if runtime_settings.github_api_token is not None
                    else None
                ),
                timeout_seconds=float(runtime_settings.network_timeout_seconds),
            )
            portfolio_fetcher = HTTPPortfolioTextFetcher(
                timeout_seconds=float(runtime_settings.network_timeout_seconds),
            )
            classification = JDClassificationConfiguration(
                configuration_ref=runtime_settings.jd_classification_configuration_ref,
                technical_indicators=runtime_settings.technical_indicators,
                non_technical_indicators=runtime_settings.non_technical_indicators,
            )
            groq_client = Groq(
                api_key=runtime_settings.groq_api_key.get_secret_value(),
                timeout=float(runtime_settings.network_timeout_seconds),
            )
            explanation_generator = GroqController(
                api_key=runtime_settings.groq_api_key.get_secret_value(),
                model_configuration=AIModelConfiguration(
                    provider="groq",
                    model=runtime_settings.groq_model,
                    model_config_ref=runtime_settings.groq_model,
                ),
                runtime_configuration=AIRuntimeConfiguration(
                    temperature=runtime_settings.groq_temperature,
                    max_tokens=runtime_settings.groq_max_tokens,
                    structured_output=True,
                ),
                client=groq_client,
            )
            dependencies = ScreeningGraphDependencies(
                classification_configuration=classification,
                linkedin_collector=LinkedInCollector(linked_in_fetcher),
                github_collector=GitHubCollector(github_fetcher),
                portfolio_collector=PortfolioCollector(portfolio_fetcher),
                scoring_release=SCORING_RELEASE_2_2_0.release,
                policy_field_presence=runtime_settings.policy_field_presence,
                policy_configuration_ref=runtime_settings.policy_configuration_ref,
                explanation_generator=explanation_generator,
            )
            app.state.screening_graph = build_screening_graph(
                dependencies=dependencies,
                checkpointer=checkpointer,
            )
            app.state.screening_id_registry = screening_registry
            app.state.application_settings = runtime_settings
            app.title = runtime_settings.app_name
            yield
        except Exception:
            raise ApplicationDependencyError(
                "production application initialization failed; verify required "
                "configuration and PostgreSQL connectivity"
            ) from None
        finally:
            if groq_client is not None:
                groq_client.close()
            if pool.closed is False:
                pool.close()

    return create_app(
        graph=None,
        lifespan=lifespan,
        title=(settings.app_name if settings is not None else "VikatHire API"),
        max_request_bytes=(
            settings.api_max_request_bytes
            if settings is not None
            else lambda: runtime["settings"].api_max_request_bytes
        ),
    )
