from vikat_hire.contracts import (
    DocumentInput,
    ExternalSourceInput,
    InputKind,
    ScreeningInput,
)


def make_document(kind: InputKind) -> DocumentInput:
    return DocumentInput(
        kind=kind,
        filename="input.pdf",
        media_type="application/pdf",
        content_hash="a" * 64,
        storage_ref="documents/test",
    )


def test_screening_input_accepts_required_documents() -> None:
    screening = ScreeningInput(
        jd=make_document(InputKind.JD),
        resume=make_document(InputKind.RESUME),
    )

    assert screening.jd.kind is InputKind.JD
    assert screening.resume.kind is InputKind.RESUME
    assert screening.external_sources.linkedin_url is None


def test_external_sources_are_optional() -> None:
    sources = ExternalSourceInput()

    assert sources.linkedin_url is None
    assert sources.github_url is None
    assert sources.portfolio_url is None