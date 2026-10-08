from __future__ import annotations

import pytest
from pydantic import ValidationError

from vikat_hire.app.settings import ApplicationSettings


def _values() -> dict[str, str]:
    return {
        "VIKATHIRE_APP_NAME": "VikatHire test",
        "VIKATHIRE_ENVIRONMENT": "test",
        "VIKATHIRE_LOG_LEVEL": "INFO",
        "VIKATHIRE_DATABASE_URL": "postgresql+psycopg://user:secret@localhost:5432/vikathire",
        "VIKATHIRE_APIFY_API_TOKEN": "apify-test-secret",
        "VIKATHIRE_APIFY_LINKEDIN_ACTOR_ID": "actor/test",
        "VIKATHIRE_GROQ_API_KEY": "groq-test-secret",
        "VIKATHIRE_GROQ_MODEL": "model/test",
        "VIKATHIRE_JD_TECHNICAL_INDICATORS": "Python, APIs",
        "VIKATHIRE_JD_NON_TECHNICAL_INDICATORS": "communications, recruiting",
        "VIKATHIRE_JD_CLASSIFICATION_CONFIGURATION_REF": "classification-test@1",
        "VIKATHIRE_POLICY_CONFIGURATION_REF": "policy-test@1",
        "VIKATHIRE_POLICY_CERTIFICATION_PRESENT": "true",
        "VIKATHIRE_POLICY_EDUCATION_PRESENT": "true",
        "VIKATHIRE_POLICY_LOCATION_PRESENT": "true",
        "VIKATHIRE_POLICY_AVAILABILITY_PRESENT": "true",
    }


def test_application_settings_validate_and_normalize_postgres_url() -> None:
    settings = ApplicationSettings(_env_file=None, **_values())

    assert settings.psycopg_conninfo == "postgresql://user:secret@localhost:5432/vikathire"
    assert settings.technical_indicators == ("Python", "APIs")
    assert settings.non_technical_indicators == ("communications", "recruiting")
    assert settings.policy_field_presence == {
        "certification": True,
        "education": True,
        "location": True,
        "availability": True,
    }


def test_application_settings_require_production_configuration() -> None:
    values = _values()
    del values["VIKATHIRE_POLICY_LOCATION_PRESENT"]

    with pytest.raises(ValidationError):
        ApplicationSettings(_env_file=None, **values)


def test_application_settings_reject_non_postgres_database() -> None:
    values = _values()
    values["VIKATHIRE_DATABASE_URL"] = "sqlite:///local.db"

    with pytest.raises(ValidationError, match="PostgreSQL"):
        ApplicationSettings(_env_file=None, **values)


def test_application_settings_reject_invalid_log_level() -> None:
    values = _values()
    values["VIKATHIRE_LOG_LEVEL"] = "not-a-level"

    with pytest.raises(ValidationError, match="logging level"):
        ApplicationSettings(_env_file=None, **values)


def test_secret_settings_are_masked_when_serialized() -> None:
    settings = ApplicationSettings(_env_file=None, **_values())

    serialized = settings.model_dump_json()

    assert "apify-test-secret" not in serialized
    assert "groq-test-secret" not in serialized
    assert "**********" in serialized
