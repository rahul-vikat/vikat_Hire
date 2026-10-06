from __future__ import annotations

import pytest
from pydantic import ValidationError

from vikat_hire.collection.collector import build_collection_result
from vikat_hire.contracts.collection import CollectionResult, CollectionStatus, CollectedSource
from vikat_hire.contracts.common import AccessStatus, InputKind, SourceType
from vikat_hire.contracts.inputs import DocumentInput, ExternalSourceInput, ScreeningInput


def _screening(external: ExternalSourceInput | None = None) -> ScreeningInput:
    def document(kind: InputKind, input_id: str, storage: str) -> DocumentInput:
        return DocumentInput(input_id=input_id, kind=kind, filename=f"{kind}.pdf", media_type="application/pdf", content_hash=f"hash-{input_id}", storage_ref=storage)
    return ScreeningInput(screening_id="screening-1", jd=document(InputKind.JD, "jd-1", "storage/jd"), resume=document(InputKind.RESUME, "resume-1", "storage/resume"), external_sources=external or ExternalSourceInput(input_id="external-1"))


def _source(result, kind):
    return next(source for source in result.sources if source.source_type is kind)


def test_documents_are_always_collected():
    result = build_collection_result(screening_input=_screening())
    for kind in (SourceType.JD_FILE, SourceType.RESUME_FILE):
        source = _source(result, kind)
        assert source.status == CollectionStatus.COLLECTED
        assert source.access_status is AccessStatus.AUTHORIZED


def test_external_without_url_is_not_applicable():
    result = build_collection_result(screening_input=_screening())
    for kind in (SourceType.LINKEDIN, SourceType.GITHUB, SourceType.PORTFOLIO):
        source = _source(result, kind)
        assert source.status == CollectionStatus.NOT_APPLICABLE
        assert source.access_status is None
        assert source.provenance_refs == ()


def test_external_authorization_states_and_defaults():
    result = build_collection_result(screening_input=_screening(ExternalSourceInput(input_id="external-1", linkedin_url="https://www.linkedin.com/in/example", github_url="https://github.com/example", github_authorized=False)))
    assert _source(result, SourceType.LINKEDIN).status == CollectionStatus.COLLECTED
    assert _source(result, SourceType.GITHUB).status == CollectionStatus.NOT_AUTHORIZED


def test_provenance_references_are_valid_and_input_is_unchanged():
    screening = _screening(ExternalSourceInput(input_id="external-1", portfolio_url="https://example.com"))
    before = screening.model_dump()
    result = build_collection_result(screening_input=screening)
    known = {p.provenance_id for p in result.provenances}
    assert all(set(source.provenance_refs) <= known for source in result.sources)
    assert screening.model_dump() == before


def test_invalid_collection_states_are_rejected():
    with pytest.raises(ValidationError):
        CollectedSource(source_type=SourceType.LINKEDIN, source_ref="x", status=CollectionStatus.COLLECTED, access_status=AccessStatus.NOT_AUTHORIZED, provenance_refs=("p",))
    with pytest.raises(ValidationError):
        CollectedSource(source_type=SourceType.LINKEDIN, source_ref="x", status=CollectionStatus.NOT_APPLICABLE, access_status=AccessStatus.AUTHORIZED, provenance_refs=())


def test_unknown_provenance_is_rejected():
    source = CollectedSource(source_type=SourceType.LINKEDIN, source_ref="x", status=CollectionStatus.NOT_AUTHORIZED, access_status=AccessStatus.NOT_AUTHORIZED, provenance_refs=("missing",))
    with pytest.raises(ValidationError):
        CollectionResult(screening_id="s", sources=(source,), provenances=())
