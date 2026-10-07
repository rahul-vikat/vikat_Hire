from __future__ import annotations

from decimal import Decimal

import pytest

from vikat_hire.config.models import AIRuntimeConfiguration


def test_ai_runtime_configuration_uses_safe_defaults() -> None:
    configuration = AIRuntimeConfiguration()

    assert configuration.temperature == Decimal("0")
    assert configuration.max_tokens == 1024
    assert configuration.structured_output is True


def test_ai_runtime_configuration_accepts_valid_values() -> None:
    configuration = AIRuntimeConfiguration(
        temperature=Decimal("0.2"),
        max_tokens=2048,
        structured_output=False,
    )

    assert configuration.temperature == Decimal("0.2")
    assert configuration.max_tokens == 2048
    assert configuration.structured_output is False


@pytest.mark.parametrize(
    "temperature",
    [
        Decimal("-0.01"),
        Decimal("2.01"),
    ],
)
def test_ai_runtime_configuration_rejects_invalid_temperature(
    temperature: Decimal,
) -> None:
    with pytest.raises(ValueError):
        AIRuntimeConfiguration(temperature=temperature)


@pytest.mark.parametrize(
    "max_tokens",
    [
        0,
        -1,
    ],
)
def test_ai_runtime_configuration_rejects_invalid_max_tokens(
    max_tokens: int,
) -> None:
    with pytest.raises(ValueError):
        AIRuntimeConfiguration(max_tokens=max_tokens)


def test_ai_runtime_configuration_is_immutable() -> None:
    configuration = AIRuntimeConfiguration()

    with pytest.raises(Exception):
        configuration.temperature = Decimal("0.5")


def test_ai_runtime_configuration_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        AIRuntimeConfiguration(
            unsupported_option=True,
        )