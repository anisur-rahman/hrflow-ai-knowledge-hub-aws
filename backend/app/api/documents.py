"""Document library and the two-step upload (record + presigned target)."""
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings, split_csv
from app.db import get_db
from app.models import IN_FLIGHT, Document, Status, new_id
from app.schemas.documents import DocId, DocumentOut, SourceLink, UploadRequest, UploadResponse
from app.security import Principal, current_principal, require_admin, visible_documents
from app.services import audit, s3_service
from app.services.ingestion import enqueue

router = APIRouter(prefix='/api/documents', tags=['documents'])


def get_visible(db: Session, document_id: str, principal: Principal) -> Document:
    doc = db.scalars(select(Document).where(Document.id == document_id, visible_documents(principal))).first()
    if doc is None:
        raise HTTPException(404, 'Document not found')
    return doc


def size_limit_error() -> HTTPException:
    return HTTPException(413, f'PDF limit is {settings.max_upload_bytes // (1024 * 1024)} MB')


@router.get('', response_model=list[DocumentOut])
def list_documents(status: Status | None = None, db: Session = Depends(get_db),
                   principal: Principal = Depends(current_principal)):
    stmt = select(Document).where(visible_documents(principal)).order_by(Document.created_at.desc()).limit(500)
    if status:
        stmt = stmt.where(Document.status == status)
    return db.scalars(stmt).all()


@router.get('/{document_id}', response_model=DocumentOut)
def get_document(document_id: DocId, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    return get_visible(db, document_id, principal)


@router.post('', status_code=201, response_model=UploadResponse)
def create_upload(req: UploadRequest, db: Session = Depends(get_db), admin: Principal = Depends(require_admin)):
    """Step 1: create the record and return where the browser sends the file (a presigned S3 POST in AWS)."""
    if req.size_bytes > settings.max_upload_bytes:
        raise size_limit_error()
    document_id = new_id()
    title = req.filename.replace('\\', '/').rsplit('/', 1)[-1][:255]
    doc = Document(id=document_id, title=title, version_label=req.version_label,
                   storage_key=s3_service.key_for(document_id), size_bytes=req.size_bytes,
                   status=Status.AWAITING_UPLOAD, uploaded_by=admin.username,
                   allowed_groups=req.allowed_groups or split_csv(settings.default_document_groups))
    db.add(doc)
    audit.record(db, admin.username, 'document.created', document_id, title=title, allowed_groups=doc.allowed_groups)
    db.commit()
    return {'document': doc, 'upload': s3_service.upload_target(document_id)}


@router.post('/{document_id}/file', status_code=202, response_model=DocumentOut)
def upload_local_file(document_id: DocId, background: BackgroundTasks, file: UploadFile = File(...),
                      db: Session = Depends(get_db), admin: Principal = Depends(require_admin)):
    """Step 2, local storage only. In AWS the browser posts to S3 and S3 -> SQS -> Lambda takes over."""
    if settings.storage_provider != 'local':
        raise HTTPException(409, 'Upload the file to the presigned S3 URL instead')
    doc = db.get(Document, document_id, with_for_update=True)
    if doc is None:
        raise HTTPException(404, 'Document not found')
    if doc.status != Status.AWAITING_UPLOAD:
        raise HTTPException(409, f'Document is {doc.status}, not awaiting upload')
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise size_limit_error()
    if not data.startswith(b'%PDF-'):
        raise HTTPException(400, 'File is not a PDF')
    s3_service.save_local(doc.storage_key, data)
    doc.status, doc.size_bytes = Status.QUEUED, len(data)
    db.commit()
    enqueue(doc.id, background)
    return doc


@router.get('/{document_id}/file')
def download_local_file(document_id: DocId, db: Session = Depends(get_db),
                        principal: Principal = Depends(current_principal)):
    if settings.storage_provider != 'local':
        raise HTTPException(404, 'Use the source link endpoint')
    doc = get_visible(db, document_id, principal)
    return FileResponse(s3_service.local_path(doc.storage_key), media_type='application/pdf',
                        headers={'Content-Disposition': 'inline', 'Cache-Control': 'private, no-store'})


@router.get('/{document_id}/source', response_model=SourceLink)
def source_link(document_id: DocId, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)):
    """A short-lived link to the original PDF, only for documents the caller may see."""
    doc = get_visible(db, document_id, principal)
    if doc.status in IN_FLIGHT:
        raise HTTPException(409, 'The file is not available yet')
    audit.record(db, principal.username, 'document.source_opened', doc.id)
    db.commit()
    return s3_service.source_url(doc.id, doc.storage_key, doc.title)
