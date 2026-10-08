from __future__ import annotations

from typing import Protocol

from vikat_hire.contracts.collection import CollectedSource
from vikat_hire.contracts.evidence import Provenance
from vikat_hire.contracts.inputs import ExternalSourceInput
from vikat_hire.contracts.normalization import ExtractedTextBlock


class ExternalCollectionError(ValueError):
    """Raised when an external-source collection result is invalid."""


class ExternalCollectionResult:
    """
    Provider-neutral result returned by an external-source adapter.

    Collection owns retrieval facts only. Normalization and evaluation remain
    separate downstream stages.
    """

    __slots__ = (
        "source",
        "provenances",
        "extracted_blocks",
    )

    def __init__(
        self,
        *,
        source: CollectedSource,
        provenances: tuple[Provenance, ...],
        extracted_blocks: tuple[ExtractedTextBlock, ...],
    ) -> None:
        self.source = source
        self.provenances = provenances
        self.extracted_blocks = extracted_blocks

        self._validate()

    def _validate(self) -> None:
        known_provenance_ids = {
            provenance.provenance_id
            for provenance in self.provenances
        }

        source_provenance_ids = set(self.source.provenance_refs)

        unknown_source_refs = (
            source_provenance_ids - known_provenance_ids
        )

        if unknown_source_refs:
            raise ExternalCollectionError(
                "source contains unknown provenance references: "
                f"{sorted(unknown_source_refs)}"
            )

        seen_block_ids: set[str] = set()

        for block in self.extracted_blocks:
            if block.block_id in seen_block_ids:
                raise ExternalCollectionError(
                    f"duplicate extracted block id: {block.block_id}"
                )

            seen_block_ids.add(block.block_id)

            if block.source_type is not self.source.source_type:
                raise ExternalCollectionError(
                    "extracted block source type does not match collected source"
                )

            if block.source_ref != self.source.source_ref:
                raise ExternalCollectionError(
                    "extracted block source reference does not match "
                    "collected source"
                )

            unknown_block_refs = (
                set(block.provenance_refs) - known_provenance_ids
            )

            if unknown_block_refs:
                raise ExternalCollectionError(
                    "extracted block contains unknown provenance references: "
                    f"{sorted(unknown_block_refs)}"
                )

        if self.source.status == "collected" and not self.extracted_blocks:
            raise ExternalCollectionError(
                "collected external source must contain extracted blocks"
            )


class ExternalSourceCollector(Protocol):
    """
    Provider-neutral external-source retrieval boundary.

    Implementations may use APIs, HTTP clients, crawlers, or another approved
    mechanism. Those implementation details must not leak into normalization,
    evaluation, scoring, or policy.
    """

    def collect(
        self,
        *,
        source_input: ExternalSourceInput,
    ) -> ExternalCollectionResult:
        ...