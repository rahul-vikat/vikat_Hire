from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from vikat_hire.ai.groq_controller import (
    GroqController,
    GroqControllerError,
)
from vikat_hire.config.models import (
    AIModelConfiguration,
    AIRuntimeConfiguration,
)


def _model_configuration() -> AIModelConfiguration:
    return AIModelConfiguration(
        provider="groq",
        model="test-model",
        model_config_ref="explanation-test-v1",
    )


def _runtime_configuration() -> AIRuntimeConfiguration:
    return AIRuntimeConfiguration(
        temperature=Decimal("0"),
        max_tokens=512,
        structured_output=True,
    )


class FakeCompletions:
    def __init__(self, response: object) -> None:
        self.response = response
        self.request: dict[str, object] | None = None

    def create(self, **kwargs: object) -> object:
        self.request = kwargs
        return self.response


class FakeClient:
    def __init__(self, response: object) -> None:
        self.completions = FakeCompletions(response)

        self.chat = SimpleNamespace(
            completions=self.completions,
        )


def _response(content: str) -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                )
            )
        ]
    )


def test_groq_controller_rejects_blank_api_key() -> None:
    with pytest.raises(GroqControllerError, match="api_key"):
        GroqController(
            api_key="   ",
            model_configuration=_model_configuration(),
            runtime_configuration=_runtime_configuration(),
        )


def test_groq_controller_rejects_non_groq_provider() -> None:
    configuration = AIModelConfiguration(
        provider="other-provider",
        model="test-model",
        model_config_ref="test-v1",
    )

    with pytest.raises(GroqControllerError, match="provider 'groq'"):
        GroqController(
            api_key="test-key",
            model_configuration=configuration,
            runtime_configuration=_runtime_configuration(),
            client=object(),
        )


def test_groq_controller_raises_for_invalid_json() -> None:
    client = FakeClient(_response("not-json"))
    controller = GroqController(
        api_key="test-key",
        model_configuration=_model_configuration(),
        runtime_configuration=_runtime_configuration(),
        client=client,
    )

    with pytest.raises(
        GroqControllerError,
        match="not valid JSON",
    ):
        controller._extract_json_payload(_response("not-json"))


def test_groq_controller_request_uses_configured_model_and_runtime() -> None:
    client = FakeClient(_response("{}"))

    controller = GroqController(
        api_key="test-key",
        model_configuration=_model_configuration(),
        runtime_configuration=_runtime_configuration(),
        client=client,
    )

    with pytest.raises(GroqControllerError):
        controller(object())  # type: ignore[arg-type]

    assert client.completions.request is None
