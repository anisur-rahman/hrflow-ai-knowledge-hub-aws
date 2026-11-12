"""HR administration: review/publish, reprocess, delete, dashboard statistics and the audit trail."""
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import IN_FLIGHT, Audit, Chunk, Document, Status, utcnow
from app.schemas.admin import AuditEventOut, Stats
from app.schemas.documents import DocId, DocumentOut, ReviewRequest
from app.security import Principal, require_admin
from app.services import audit, s3_service
from app.services.ingestion import STUCK_AFTER, enqueue

router = APIRouter(tags=['admin'])

REVIEWABLE_FROM = {'approve': {Status.PENDING_REVIEW, Status.PUBLISHED, Status.REJECTED},
                   'reject': {Status.PENDING_REVIEW, Status.PUBLISHED}}


def get_for_update(db: Session, document_id: str) -> Document:
    doc = db.get(Document, document_id, with_for_update=True)
    if doc is None:
        raise HTTPException(404, 'Document not found')
    return doc


@router.patch('/api/documents/{document_id}/review', response_model=DocumentOut)
def review_document(document_id: DocId, req: ReviewRequest, db: Session = Depends(get_db),
                    admin: Principal = Depends(require_admin)):
    doc = get_for_update(db, document_id)
    if doc.status not in REVIEWABLE_FROM[req.action]:
        raise HTTPException(409, f'Cannot {req.action} a document that is {doc.status}')
    changes = req.model_dump(exclude_none=True, exclude={'action', 'note'})
    for name, value in changes.items():
        setattr(doc, name, value)
    if req.action == 'approve' and not (doc.summary or '').strip():
        raise HTTPException(422, 'A summary is required before publishing')
    doc.status = Status.PUBLISHED if req.action == 'approve' else Status.REJECTED
    doc.reviewed_by, doc.reviewed_at = admin.username, utcnow()
    audit.record(db, admin.username, f'document.{req.action}d', doc.id, changed=sorted(changes), note=req.note,
                 ai_summary_edited=doc.summary != doc.ai_summary, ai_category_overridden=doc.category != doc.ai_category)
    db.commit()
    return doc


@router.post('/api/documents/{document_id}/reprocess', status_code=202, response_model=DocumentOut)
def reprocess_document(document_id: DocId, background: BackgroundTasks, db: Session = Depends(get_db),
                       admin: Principal = Depends(require_admin)):
    """Re-run ingestion (after a failure, a model change, or a job stuck for over an hour).
    Published documents go back to review."""
    doc = get_for_update(db, document_id)
    if doc.status in IN_FLIGHT and doc.updated_at > utcnow() - STUCK_AFTER:
        raise HTTPException(409, f'Document is already {doc.status}')
    doc.status, doc.status_detail, doc.textract_job_id = Status.QUEUED, None, None
    audit.record(db, admin.username, 'document.reprocess_requested', doc.id)
    db.commit()
    enqueue(doc.id, background)
    return doc


@router.delete('/api/documents/{document_id}', status_code=204)
def delete_document(document_id: DocId, db: Session = Depends(get_db), admin: Principal = Depends(require_admin)):
    doc = get_for_update(db, document_id)
    if doc.status == Status.PROCESSING:
        raise HTTPException(409, 'Wait for processing to finish before deleting')
    s3_service.delete(doc.storage_key)  # storage first: a failure leaves the record, not an orphaned file
    audit.record(db, admin.username, 'document.deleted', doc.id, title=doc.title)
    db.delete(doc)
    db.commit()


@router.get('/api/admin/stats', response_model=Stats)
def stats(db: Session = Depends(get_db), _: Principal = Depends(require_admin)):
    since = utcnow() - timedelta(days=7)
    questions = select(Audit).where(Audit.action == 'chat.asked', Audit.created_at >= since).subquery()
    return Stats(
        documents_by_status=dict(db.execute(select(Document.status, func.count()).group_by(Document.status)).all()),
        searchable_chunks=db.scalar(select(func.count()).select_from(Chunk).join(Document)
                                    .where(Document.status == Status.PUBLISHED)) or 0,
        questions_7d=db.scalar(select(func.count()).select_from(questions)) or 0,
        unanswered_7d=db.scalar(select(func.count()).select_from(questions).where(
            func.jsonb_array_length(questions.c.details['source_document_ids']) == 0)) or 0,
    )


@router.get('/api/admin/audit-events', response_model=list[AuditEventOut])
def audit_events(limit: int = Query(25, ge=1, le=200), document_id: DocId | None = None,
                 db: Session = Depends(get_db), _: Principal = Depends(require_admin)):
    stmt = select(Audit).order_by(Audit.created_at.desc()).limit(limit)
    if document_id:
        stmt = stmt.where(Audit.document_id == document_id)
    return db.scalars(stmt).all()
