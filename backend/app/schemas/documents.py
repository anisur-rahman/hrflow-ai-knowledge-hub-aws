from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.services.classification import CATEGORIES, UNCATEGORIZED

GroupName = Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_.-]{1,64}$')]
DocId = Annotated[str, StringConstraints(pattern=r'^[0-9a-f-]{36}$')]
# Built from the classifier's list so the review API always accepts what the AI can propose.
Category = Literal[(*CATEGORIES, UNCATEGORIZED)]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    version_label: str | None
    status: str
    status_detail: str | None
    category: str | None
    summary: str | None
    ai_category: str | None
    ai_summary: str | None
    allowed_groups: list[str]
    page_count: int | None
    chunk_count: int | None
    size_bytes: int | None
    extraction_method: str | None
    uploaded_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UploadRequest(BaseModel):
    filename: str = Field(min_length=5, max_length=255)
    size_bytes: int = Field(gt=0)
    version_label: str | None = Field(default=None, max_length=50)
    allowed_groups: list[GroupName] | None = Field(default=None, min_length=1, max_length=20)

    @field_validator('filename')
    @classmethod
    def must_be_pdf(cls, value: str) -> str:
        if not value.lower().endswith('.pdf'):
            raise ValueError('Only PDF files are supported')
        return value


class UploadTarget(BaseModel):
    url: str
    fields: dict[str, str]
    requires_auth: bool


class UploadResponse(BaseModel):
    document: DocumentOut
    upload: UploadTarget


class SourceLink(BaseModel):
    url: str
    requires_auth: bool


class ReviewRequest(BaseModel):
    action: Literal['approve', 'reject']
    category: Category | None = None
    summary: str | None = Field(default=None, max_length=2000)
    version_label: str | None = Field(default=None, max_length=50)
    allowed_groups: list[GroupName] | None = Field(default=None, min_length=1, max_length=20)
    note: str | None = Field(default=None, max_length=500)
