from __future__ import annotations

from vikat_hire.contracts.collection import CollectionResult, CollectionStatus, CollectedSource
from vikat_hire.contracts.common import AccessStatus, DerivationMethod, Provenance, SourceType
from vikat_hire.contracts.inputs import ScreeningInput


def _document_source(*, source_type: SourceType, source_ref: str, storage_ref: str) -> tuple[CollectedSource, Provenance]:
    provenance = Provenance(source_type=source_type, source_ref=source_ref, method=DerivationMethod.RULE, access_status=AccessStatus.AUTHORIZED)
    source = CollectedSource(source_type=source_type, source_ref=storage_ref, access_status=AccessStatus.AUTHORIZED, status=CollectionStatus.COLLECTED, provenance_refs=(provenance.provenance_id,))
    return source, provenance


def _external_source(*, source_type: SourceType, source_ref: str, source_uri: str | None, authorized: bool) -> tuple[CollectedSource, Provenance | None]:
    if source_uri is None:
        return CollectedSource(source_type=source_type, source_ref=source_ref, access_status=None, status=CollectionStatus.NOT_APPLICABLE, provenance_refs=()), None
    access = AccessStatus.AUTHORIZED if authorized else AccessStatus.NOT_AUTHORIZED
    status = CollectionStatus.COLLECTED if authorized else CollectionStatus.NOT_AUTHORIZED
    provenance = Provenance(source_type=source_type, source_ref=source_ref, source_uri=source_uri, method=DerivationMethod.RULE, access_status=access)
    source = CollectedSource(source_type=source_type, source_ref=source_ref, source_uri=source_uri, access_status=access, status=status, provenance_refs=(provenance.provenance_id,))
    return source, provenance


def build_collection_result(*, screening_input: ScreeningInput) -> CollectionResult:
    sources: list[CollectedSource] = []
    provenances: list[Provenance] = []
    for source_type, document in ((SourceType.JD_FILE, screening_input.jd), (SourceType.RESUME_FILE, screening_input.resume)):
        source, provenance = _document_source(source_type=source_type, source_ref=document.input_id, storage_ref=document.storage_ref)
        sources.append(source)
        provenances.append(provenance)
    external = screening_input.external_sources
    definitions = ((SourceType.LINKEDIN, external.linkedin_url, external.linkedin_authorized), (SourceType.GITHUB, external.github_url, external.github_authorized), (SourceType.PORTFOLIO, external.portfolio_url, external.portfolio_authorized))
    for source_type, url, authorized in definitions:
        source, provenance = _external_source(source_type=source_type, source_ref=external.input_id, source_uri=str(url) if url is not None else None, authorized=authorized)
        sources.append(source)
        if provenance is not None:
            provenances.append(provenance)
    return CollectionResult(screening_id=screening_input.screening_id, sources=tuple(sources), provenances=tuple(provenances))
