from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import new_id, utcnow


class Status(StrEnum):
    AWAITING_UPLOAD = 'awaiting_upload'  # record created, browser is uploading to storage
    QUEUED = 'queued'
    PROCESSING = 'processing'
    OCR_PENDING = 'ocr_pending'  # Textract job running; finished by the textract_callback worker
    PENDING_REVIEW = 'pending_review'  # AI output ready, waiting for HR approval
    PUBLISHED = 'published'  # the only status the assistant may retrieve from
    REJECTED = 'rejected'
    FAILED = 'failed'


IN_FLIGHT = {Status.AWAITING_UPLOAD, Status.QUEUED, Status.PROCESSING, Status.OCR_PENDING}


class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255))
    version_label: Mapped[str | None] = mapped_column(String(50))
    storage_key: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    extraction_method: Mapped[str | None] = mapped_column(String(20))
    textract_job_id: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(30), default=Status.AWAITING_UPLOAD, index=True)
    status_detail: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ai_category: Mapped[str | None] = mapped_column(String(80))
    ai_summary: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(80))
    summary: Mapped[str | None] = mapped_column(Text)
    allowed_groups: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    uploaded_by: Mapped[str] = mapped_column(String(128))
    reviewed_by: Mapped[str | None] = mapped_column(String(128))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
