from __future__ import annotations

import logging
from decimal import Decimal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationSettingsError(ValueError):
    """Raised when required application configuration is invalid."""


class ApplicationSettings(BaseSettings):
    """Environment-backed settings for the production application boundary."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        hide_input_in_errors=True,
    )

    app_name: str = Field(validation_alias="VIKATHIRE_APP_NAME")
    environment: str = Field(validation_alias="VIKATHIRE_ENVIRONMENT")
    log_level: str = Field(validation_alias="VIKATHIRE_LOG_LEVEL")
    database_url: SecretStr = Field(validation_alias="VIKATHIRE_DATABASE_URL")

    apify_api_token: SecretStr = Field(validation_alias="VIKATHIRE_APIFY_API_TOKEN")
    apify_linkedin_actor_id: str = Field(validation_alias="VIKATHIRE_APIFY_LINKEDIN_ACTOR_ID")
    github_api_token: SecretStr | None = Field(
        default=None,
        validation_alias="VIKATHIRE_GITHUB_API_TOKEN",
    )

    groq_api_key: SecretStr = Field(validation_alias="VIKATHIRE_GROQ_API_KEY")
    groq_model: str = Field(validation_alias="VIKATHIRE_GROQ_MODEL")
    groq_temperature: Decimal = Field(
        default=Decimal("0.1"),
        validation_alias="VIKATHIRE_GROQ_TEMPERATURE",
    )
    groq_max_tokens: int = Field(
        default=4096,
        validation_alias="VIKATHIRE_GROQ_MAX_TOKENS",
        gt=0,
    )

    jd_technical_indicators: str = Field(validation_alias="VIKATHIRE_JD_TECHNICAL_INDICATORS")
    jd_non_technical_indicators: str = Field(
        validation_alias="VIKATHIRE_JD_NON_TECHNICAL_INDICATORS"
    )
    jd_classification_configuration_ref: str = Field(
        validation_alias="VIKATHIRE_JD_CLASSIFICATION_CONFIGURATION_REF"
    )

    policy_configuration_ref: str = Field(validation_alias="VIKATHIRE_POLICY_CONFIGURATION_REF")
    policy_certification_present: bool = Field(
        validation_alias="VIKATHIRE_POLICY_CERTIFICATION_PRESENT"
    )
    policy_education_present: bool = Field(validation_alias="VIKATHIRE_POLICY_EDUCATION_PRESENT")
    policy_location_present: bool = Field(validation_alias="VIKATHIRE_POLICY_LOCATION_PRESENT")
    policy_availability_present: bool = Field(
        validation_alias="VIKATHIRE_POLICY_AVAILABILITY_PRESENT"
    )

    api_max_request_bytes: int = Field(
        default=20 * 1024 * 1024,
        validation_alias="VIKATHIRE_API_MAX_REQUEST_BYTES",
        gt=0,
    )
    network_timeout_seconds: Decimal = Field(
        default=Decimal("30"),
        validation_alias="VIKATHIRE_NETWORK_TIMEOUT_SECONDS",
        gt=Decimal("0"),
    )
    apify_timeout_seconds: Decimal = Field(
        default=Decimal("60"),
        validation_alias="VIKATHIRE_APIFY_TIMEOUT_SECONDS",
        gt=Decimal("0"),
    )
    apify_poll_interval_seconds: Decimal = Field(
        default=Decimal("1"),
        validation_alias="VIKATHIRE_APIFY_POLL_INTERVAL_SECONDS",
        ge=Decimal("0"),
    )
    postgres_pool_min_size: int = Field(
        default=1,
        validation_alias="VIKATHIRE_POSTGRES_POOL_MIN_SIZE",
        ge=1,
    )
    postgres_pool_max_size: int = Field(
        default=10,
        validation_alias="VIKATHIRE_POSTGRES_POOL_MAX_SIZE",
        ge=1,
    )

    @field_validator(
        "app_name",
        "environment",
        "log_level",
        "apify_linkedin_actor_id",
        "groq_model",
        "jd_technical_indicators",
        "jd_non_technical_indicators",
        "jd_classification_configuration_ref",
        "policy_configuration_ref",
    )
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("setting must not be blank")
        return value.strip()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not isinstance(logging.getLevelName(normalized), int):
            raise ValueError("log level must be a standard Python logging level")
        return normalized

    @field_validator("groq_temperature")
    @classmethod
    def validate_temperature(cls, value: Decimal) -> Decimal:
        if not Decimal("0") <= value <= Decimal("2"):
            raise ValueError("GROQ temperature must be between 0 and 2")
        return value

    @model_validator(mode="after")
    def validate_application_settings(self) -> ApplicationSettings:
        database_url = self.database_url.get_secret_value()
        parts = urlsplit(database_url)
        if parts.scheme not in {"postgresql", "postgresql+psycopg", "postgres"}:
            raise ValueError("database URL must use PostgreSQL with psycopg")
        if not parts.hostname or not parts.path.strip("/"):
            raise ValueError("database URL must include a host and database name")
        if self.postgres_pool_min_size > self.postgres_pool_max_size:
            raise ValueError("PostgreSQL pool minimum cannot exceed maximum")
        if not self.apify_api_token.get_secret_value().strip():
            raise ValueError("Apify API token must not be blank")
        if not self.groq_api_key.get_secret_value().strip():
            raise ValueError("Groq API key must not be blank")
        if self.jd_technical_indicators.casefold() == self.jd_non_technical_indicators.casefold():
            raise ValueError("JD classification indicator sets must be distinct")
        return self

    @property
    def psycopg_conninfo(self) -> str:
        """Return the SQLAlchemy-style configured URL in psycopg form."""
        value = self.database_url.get_secret_value()
        if value.startswith("postgresql+psycopg://"):
            return value.replace("postgresql+psycopg://", "postgresql://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql://", 1)
        return value

    @property
    def technical_indicators(self) -> tuple[str, ...]:
        return _split_indicators(self.jd_technical_indicators)

    @property
    def non_technical_indicators(self) -> tuple[str, ...]:
        return _split_indicators(self.jd_non_technical_indicators)

    @property
    def policy_field_presence(self) -> dict[str, bool]:
        return {
            "certification": self.policy_certification_present,
            "education": self.policy_education_present,
            "location": self.policy_location_present,
            "availability": self.policy_availability_present,
        }


def _split_indicators(value: str) -> tuple[str, ...]:
    indicators = tuple(item.strip() for item in value.split(",") if item.strip())
    if not indicators:
        raise ApplicationSettingsError("JD classification indicators must not be empty")
    return indicators
