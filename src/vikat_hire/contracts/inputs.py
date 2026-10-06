from __future__ import annotations

from datetime import datetime

from pydantic import Field, HttpUrl

from .common import ContractModel, InputKind, new_id, utc_now


class DocumentInput(ContractModel):
    input_id: str = Field(default_factory=new_id)
    kind: InputKind

    filename: str
    media_type: str
    content_hash: str

    storage_ref: str

    created_at: datetime = Field(default_factory=utc_now)


class ExternalSourceInput(ContractModel):
    input_id: str = Field(default_factory=new_id)

    linkedin_url: HttpUrl | None = None
    github_url: HttpUrl | None = None
    portfolio_url: HttpUrl | None = None

    linkedin_authorized: bool = True
    github_authorized: bool = True
    portfolio_authorized: bool = True


class ScreeningInput(ContractModel):
    screening_id: str = Field(default_factory=new_id)

    jd: DocumentInput
    resume: DocumentInput

    external_sources: ExternalSourceInput = Field(
        default_factory=ExternalSourceInput
    )

    created_at: datetime = Field(default_factory=utc_now)
