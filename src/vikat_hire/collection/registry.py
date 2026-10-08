from __future__ import annotations

from collections.abc import Mapping

from vikat_hire.collection.external import (
    ExternalCollectionResult,
    ExternalSourceCollector,
)
from vikat_hire.contracts.common import SourceType
from vikat_hire.contracts.inputs import ExternalSourceInput

_EXTERNAL_SOURCE_TYPES = frozenset(
    {
        SourceType.LINKEDIN,
        SourceType.GITHUB,
        SourceType.PORTFOLIO,
    }
)


class ExternalCollectorRegistryError(ValueError):
    """Raised when external collector registration or lookup is invalid."""


class ExternalCollectorRegistry:
    """
    Provider-neutral registry for external-source collectors.

    The registry only performs deterministic source-type dispatch.
    Provider implementations own all retrieval mechanics.
    """

    def __init__(
        self,
        collectors: Mapping[SourceType, ExternalSourceCollector],
    ) -> None:
        normalized = dict(collectors)

        unsupported = set(normalized) - _EXTERNAL_SOURCE_TYPES
        if unsupported:
            raise ExternalCollectorRegistryError(
                "unsupported external source types: "
                f"{sorted(source.value for source in unsupported)}"
            )

        for source_type, collector in normalized.items():
            if not callable(getattr(collector, "collect", None)):
                raise ExternalCollectorRegistryError(
                    f"collector for {source_type.value} must provide collect()"
                )

        self._collectors = normalized

    def has_collector(self, source_type: SourceType) -> bool:
        """Return whether a collector is registered for the source type."""
        return source_type in self._collectors

    def collect(
        self,
        *,
        source_type: SourceType,
        source_input: ExternalSourceInput,
    ) -> ExternalCollectionResult:
        """
        Dispatch collection to the registered provider.

        This method does not interpret, normalize, evaluate, score, or alter
        the provider result.
        """
        if source_type not in _EXTERNAL_SOURCE_TYPES:
            raise ExternalCollectorRegistryError(
                f"unsupported external source type: {source_type.value}"
            )

        collector = self._collectors.get(source_type)

        if collector is None:
            raise ExternalCollectorRegistryError(
                f"no collector registered for {source_type.value}"
            )

        result = collector.collect(source_input=source_input)

        if not isinstance(result, ExternalCollectionResult):
            raise ExternalCollectorRegistryError(
                f"collector for {source_type.value} returned "
                "an invalid result type"
            )

        if result.source.source_type is not source_type:
            raise ExternalCollectorRegistryError(
                f"collector for {source_type.value} returned "
                f"{result.source.source_type.value}"
            )

        return result