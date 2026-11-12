"""Ingestion pipeline: extract -> classify -> summarize -> chunk -> embed -> store for HR review.

Two entry points, both idempotent and safe to retry from SQS:
  start_ingestion  S3 upload event (workers/ingest_lambda) or local background task. Digital PDFs are
                   finished immediately; scanned PDFs start an async Textract job and stop.
  finish_ocr       Textract completion via SNS -> SQS (workers/textract_callback).
"""
import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import timedelta
from functools import lru_cache

import boto3
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Document, Status, utcnow
from app.observability import log_event
from app.services import extraction, s3_service, vector_store
from app.services.chunking import build_chunks
from app.services.classification import classify
from app.services.embeddings import embed_many
from app.services.extraction import IngestionError, PageText
from app.services.summarization import summarize

PROCESSING_LEASE = timedelta(minutes=15)  # Lambda maximum duration: an older PROCESSING claim is abandoned
STUCK_AFTER = timedelta(hours=1)  # in-flight this long: admins may force a reprocess
CLAIMABLE = {Status.AWAITING_UPLOAD, Status.QUEUED, Status.FAILED}


def start_ingestion(db: Session, document_id: str) -> str:
    """Returns 'succeeded', 'ocr_started', 'failed' (permanent) or 'skipped'. Raises on transient errors."""
    doc = db.scalars(select(Document).where(Document.id == document_id).with_for_update(skip_locked=True)).first()
    stale = doc is not None and doc.status == Status.PROCESSING and doc.updated_at < utcnow() - PROCESSING_LEASE
    if doc is None or (doc.status not in CLAIMABLE and not stale):
        return _skip(db, document_id, doc.status if doc else 'missing_or_locked')
    doc.status, doc.status_detail, doc.textract_job_id = Status.PROCESSING, None, None
    doc.attempts += 1
    db.commit()
    return _guarded(db, doc, lambda: _extract(db, doc), retry_status=Status.FAILED)


def finish_ocr(db: Session, job_id: str, job_status: str) -> str:
    doc = db.scalars(select(Document).where(Document.textract_job_id == job_id)
                     .with_for_update(skip_locked=True)).first()
    if doc is None or doc.status != Status.OCR_PENDING:
        return _skip(db, doc.id if doc else None, doc.status if doc else 'unknown_job', job_id=job_id)
    doc.status = Status.PROCESSING
    db.commit()

    def collect():
        if job_status not in ('SUCCEEDED', 'PARTIAL_SUCCESS'):
            raise IngestionError(f'OCR job ended with status {job_status}')
        pages = extraction.textract_pages(job_id)
        if not extraction.has_text(pages):
            raise IngestionError('OCR found no text in this document')
        return _complete(db, doc, pages, 'textract')
    # A transient error returns the document to OCR_PENDING so the SQS retry can finish it.
    return _guarded(db, doc, collect, retry_status=Status.OCR_PENDING)


def _extract(db: Session, doc: Document) -> dict:
    data = s3_service.read(doc.storage_key)
    if len(data) > settings.max_upload_bytes:
        raise IngestionError('File exceeds the upload size limit')
    pages = extraction.extract_pages(data)
    doc.size_bytes, doc.content_sha256 = len(data), hashlib.sha256(data).hexdigest()
    if extraction.has_text(pages):
        return _complete(db, doc, pages, 'text')
    if settings.ocr_provider != 'textract':
        raise IngestionError('No selectable text found. Scanned PDFs need OCR (OCR_PROVIDER=textract).')
    doc.textract_job_id = extraction.start_textract(doc.storage_key, doc.id)
    doc.status, doc.extraction_method = Status.OCR_PENDING, 'textract'
    db.commit()
    return {'outcome': 'ocr_started', 'textract_job_id': doc.textract_job_id}


def _complete(db: Session, doc: Document, pages: list[PageText], method: str) -> dict:
    full_text = '\n'.join(page.text for page in pages)
    category, summary = classify(full_text), summarize(full_text)
    pieces = build_chunks(pages)
    vectors = embed_many([f'{doc.title}\n{heading or ""}\n{content}' for _, _, heading, content in pieces])
    vector_store.replace_chunks(db, doc.id, pieces, vectors)
    doc.page_count, doc.chunk_count, doc.extraction_method = len(pages), len(pieces), method
    doc.ai_category, doc.ai_summary = category, summary
    doc.category, doc.summary = category, summary  # HR edits these during review
    doc.status, doc.processed_at = Status.PENDING_REVIEW, utcnow()
    db.commit()
    return {'outcome': 'succeeded', 'pages': len(pages), 'chunks': len(pieces), 'extraction_method': method}


def _guarded(db: Session, doc: Document, work: Callable[[], dict], retry_status: Status) -> str:
    document_id, started = doc.id, time.perf_counter()
    try:
        stats = work()
    except IngestionError as exc:
        db.rollback()
        _set_status(db, document_id, Status.FAILED, str(exc))
        log_event('ingestion.completed', document_id=document_id, outcome='failed', reason=str(exc),
                  duration_ms=_ms(started))
        return 'failed'
    except Exception as exc:
        db.rollback()
        _set_status(db, document_id, retry_status,
                    f'Temporary processing error ({type(exc).__name__}). It is retried automatically; '
                    'use Reprocess if it stays stuck.')
        log_event('ingestion.completed', level=logging.ERROR, exc_info=True, document_id=document_id,
                  outcome='error', error=type(exc).__name__, duration_ms=_ms(started))
        raise
    outcome = stats.pop('outcome')
    event = 'ingestion.completed' if outcome == 'succeeded' else 'ingestion.ocr_started'
    log_event(event, document_id=document_id, outcome=outcome, duration_ms=_ms(started), **stats)
    return outcome


def _set_status(db: Session, document_id: str, status: Status, detail: str) -> None:
    try:
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status, doc.status_detail = status, detail[:500]
            db.commit()
    except Exception:
        db.rollback()
        log_event('ingestion.status_update_failed', level=logging.ERROR, exc_info=True, document_id=document_id)


def _skip(db: Session, document_id: str | None, reason: str, **fields) -> str:
    db.rollback()
    log_event('ingestion.skipped', document_id=document_id, status=reason, **fields)
    return 'skipped'


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


# ---------- dispatch ----------

def enqueue(document_id: str, background: BackgroundTasks) -> None:
    """AWS: SQS message for the ingest worker. Local: run after the response in this process."""
    if settings.ingestion_queue_url:
        _sqs().send_message(QueueUrl=settings.ingestion_queue_url, MessageBody=json.dumps({'document_id': document_id}))
    else:
        background.add_task(ingest_in_new_session, document_id)


def ingest_in_new_session(document_id: str) -> None:
    with SessionLocal() as db:
        try:
            start_ingestion(db, document_id)
        except Exception:  # already logged and recorded on the document
            return


@lru_cache
def _sqs():
    return boto3.client('sqs', region_name=settings.aws_region)
