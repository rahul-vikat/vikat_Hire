import pytest

from vikat_hire.config import (
    SCORING_CONFIGURATION_2_2_0,
    available_scoring_releases,
    get_scoring_configuration,
)


def test_2_2_0_is_registered() -> None:
    assert (
        "verifyhire-scoring@2.2.0"
        in available_scoring_releases()
    )


def test_release_lookup_returns_authoritative_configuration() -> None:
    configuration = get_scoring_configuration(
        "verifyhire-scoring@2.2.0"
    )

    assert configuration is SCORING_CONFIGURATION_2_2_0


def test_available_releases_are_stable_and_sorted() -> None:
    releases = available_scoring_releases()

    assert releases == tuple(sorted(releases))
    assert releases == ("verifyhire-scoring@2.2.0",)


def test_unknown_release_fails_loudly() -> None:
    with pytest.raises(KeyError, match="unknown scoring release"):
        get_scoring_configuration("verifyhire-scoring@9.9.9")