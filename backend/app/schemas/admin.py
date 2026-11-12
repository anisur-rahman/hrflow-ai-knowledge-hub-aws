from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor: str
    action: str
    document_id: str | None
    details: dict
    created_at: datetime


class Stats(BaseModel):
    documents_by_status: dict[str, int]
    searchable_chunks: int
    questions_7d: int
    unanswered_7d: int  # questions where no authorized evidence was found
