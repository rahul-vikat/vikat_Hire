import pytest

from vikat_hire.config.models import AIModelConfiguration


def test_ai_model_configuration_accepts_provider_neutral_values() -> None:
    configuration = AIModelConfiguration(
        provider="groq",
        model="some-model",
        model_config_ref="ai-explanation-v1",
    )

    assert configuration.provider == "groq"
    assert configuration.model == "some-model"
    assert configuration.model_config_ref == "ai-explanation-v1"


def test_ai_model_configuration_is_provider_neutral() -> None:
    groq = AIModelConfiguration(
        provider="groq",
        model="model-a",
        model_config_ref="config-a",
    )

    future_provider = AIModelConfiguration(
        provider="future-provider",
        model="model-b",
        model_config_ref="config-b",
    )

    assert groq.provider != future_provider.provider
    assert future_provider.provider == "future-provider"


def test_ai_model_configuration_is_immutable() -> None:
    configuration = AIModelConfiguration(
        provider="groq",
        model="model-a",
        model_config_ref="config-a",
    )

    with pytest.raises(Exception):
        configuration.provider = "another-provider"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", ""),
        ("provider", "   "),
        ("model", ""),
        ("model", "   "),
        ("model_config_ref", ""),
        ("model_config_ref", "   "),
    ],
)
def test_ai_model_configuration_rejects_blank_values(
    field: str,
    value: str,
) -> None:
    values = {
        "provider": "groq",
        "model": "model-a",
        "model_config_ref": "config-a",
    }
    values[field] = value

    with pytest.raises(ValueError):
        AIModelConfiguration(**values)


def test_ai_model_configuration_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        AIModelConfiguration(
            provider="groq",
            model="model-a",
            model_config_ref="config-a",
            api_key="must-not-be-here",
        )