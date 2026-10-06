from __future__ import annotations

from types import MappingProxyType

from .models import ImmutableScoringConfiguration
from .scoring_2_2_0 import SCORING_CONFIGURATION_2_2_0


_RELEASES: dict[str, ImmutableScoringConfiguration] = {
    SCORING_CONFIGURATION_2_2_0.release.release: SCORING_CONFIGURATION_2_2_0,
}

SCORING_RELEASES = MappingProxyType(_RELEASES)


def get_scoring_configuration(
    release: str,
) -> ImmutableScoringConfiguration:
    """
    Return an immutable scoring configuration by exact release identifier.

    Raises:
        KeyError: if the requested release is not registered.
    """

    try:
        return SCORING_RELEASES[release]
    except KeyError as exc:
        available = ", ".join(sorted(SCORING_RELEASES))
        raise KeyError(
            f"unknown scoring release {release!r}; "
            f"available releases: {available}"
        ) from exc


def available_scoring_releases() -> tuple[str, ...]:
    """Return all registered scoring releases in stable order."""

    return tuple(sorted(SCORING_RELEASES))