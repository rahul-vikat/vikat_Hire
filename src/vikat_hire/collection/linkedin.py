from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from vikat_hire.collection.external import (
    ExternalCollectionError,
    ExternalCollectionResult,
)
from vikat_hire.contracts.collection import (
    CollectedSource,
    CollectionStatus,
)
from vikat_hire.contracts.common import (
    AccessStatus,
    DerivationMethod,
    Provenance,
    SourceType,
)
from vikat_hire.contracts.inputs import ExternalSourceInput
from vikat_hire.contracts.normalization import (
    ExtractedTextBlock,
    ExtractionKind,
)


class LinkedInCollectionError(ValueError):
    """Raised when LinkedIn collection input or output is invalid."""


class LinkedInFetcher(Protocol):
    """
    Retrieval-only boundary for LinkedIn content.

    The concrete implementation may use an approved API, HTTP client,
    or other retrieval mechanism. The collector remains provider-neutral.
    """

    def fetch(self, *, url: str) -> str:
        ...


class LinkedInCollector:
    """
    Provider adapter for LinkedIn collection.

    Retrieval is injected through LinkedInFetcher. This class does not
    normalize, match, evaluate, score, or decide eligibility.
    """

    def __init__(self, fetcher: LinkedInFetcher) -> None:
        if not callable(getattr(fetcher, "fetch", None)):
            raise LinkedInCollectionError(
                "LinkedIn fetcher must provide fetch()"
            )

        self._fetcher = fetcher

    def collect(
        self,
        *,
        source_input: ExternalSourceInput,
    ) -> ExternalCollectionResult:
        if source_input.linkedin_url is None:
            return self._not_applicable()

        if not source_input.linkedin_authorized:
            return self._not_authorized(
                url=str(source_input.linkedin_url),
            )

        url = str(source_input.linkedin_url)
        text = self._fetcher.fetch(url=url)

        if not isinstance(text, str):
            raise LinkedInCollectionError(
                "LinkedIn fetcher must return text"
            )

        if not text.strip():
            raise LinkedInCollectionError(
                "LinkedIn fetcher returned empty content"
            )

        source_ref = self._source_ref(source_input)
        retrieved_at = datetime.now(UTC)
        content_hash = sha256(text.encode("utf-8")).hexdigest()

        provenance = Provenance(
            source_type=SourceType.LINKEDIN,
            source_ref=source_ref,
            source_uri=url,
            retrieved_at=retrieved_at,
            observed_at=retrieved_at,
            content_hash=content_hash,
            method=DerivationMethod.CRAWLER,
            access_status=AccessStatus.AUTHORIZED,
        )

        source = CollectedSource(
            source_type=SourceType.LINKEDIN,
            source_ref=source_ref,
            source_uri=url,
            access_status=AccessStatus.AUTHORIZED,
            status=CollectionStatus.COLLECTED,
            provenance_refs=(provenance.provenance_id,),
        )

        block = ExtractedTextBlock(
            block_id=f"{source_ref}:content",
            source_type=SourceType.LINKEDIN,
            source_ref=source_ref,
            text=text,
            extraction_kind=ExtractionKind.PLAIN_TEXT,
            provenance_refs=(provenance.provenance_id,),
        )

        try:
            return ExternalCollectionResult(
                source=source,
                provenances=(provenance,),
                extracted_blocks=(block,),
            )
        except ExternalCollectionError as exc:
            raise LinkedInCollectionError(str(exc)) from exc

    @staticmethod
    def _source_ref(source_input: ExternalSourceInput) -> str:
        return f"linkedin-{source_input.input_id}"

    @classmethod
    def _not_applicable(cls) -> ExternalCollectionResult:
        source = CollectedSource(
            source_type=SourceType.LINKEDIN,
            source_ref="linkedin-not-applicable",
            source_uri=None,
            access_status=None,
            status=CollectionStatus.NOT_APPLICABLE,
            provenance_refs=(),
        )

        return ExternalCollectionResult(
            source=source,
            provenances=(),
            extracted_blocks=(),
        )

    @classmethod
    def _not_authorized(
        cls,
        *,
        url: str,
    ) -> ExternalCollectionResult:
        source_ref = "linkedin-not-authorized"

        provenance = Provenance(
            source_type=SourceType.LINKEDIN,
            source_ref=source_ref,
            source_uri=url,
            method=DerivationMethod.RULE,
            access_status=AccessStatus.NOT_AUTHORIZED,
        )

        source = CollectedSource(
            source_type=SourceType.LINKEDIN,
            source_ref=source_ref,
            source_uri=url,
            access_status=AccessStatus.NOT_AUTHORIZED,
            status=CollectionStatus.NOT_AUTHORIZED,
            provenance_refs=(provenance.provenance_id,),
        )

        return ExternalCollectionResult(
            source=source,
            provenances=(provenance,),
            extracted_blocks=(),
        )