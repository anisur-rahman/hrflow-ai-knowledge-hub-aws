"""Document storage. In AWS the browser uploads straight to a private S3 bucket with a
presigned POST; locally the file goes through the API to a Docker volume."""
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config

from app.config import settings

UPLOAD_URL_TTL = 900
DOWNLOAD_URL_TTL = 300


def key_for(document_id: str) -> str:
    return f'uploads/{document_id}.pdf'


@lru_cache
def _s3():
    return boto3.client('s3', region_name=settings.aws_region,
                        endpoint_url=f'https://s3.{settings.aws_region}.amazonaws.com',
                        config=Config(signature_version='s3v4', s3={'addressing_style': 'virtual'}))


def upload_target(document_id: str) -> dict:
    """Where the browser should POST the file (multipart form, file field last)."""
    if settings.storage_provider == 's3':
        post = _s3().generate_presigned_post(
            Bucket=settings.document_bucket, Key=key_for(document_id),
            Fields={'Content-Type': 'application/pdf'},
            Conditions=[{'Content-Type': 'application/pdf'}, ['content-length-range', 1, settings.max_upload_bytes]],
            ExpiresIn=UPLOAD_URL_TTL)
        return {'url': post['url'], 'fields': post['fields'], 'requires_auth': False}
    return {'url': f'/api/documents/{document_id}/file', 'fields': {}, 'requires_auth': True}


def source_url(document_id: str, key: str, title: str) -> dict:
    """A short-lived link to the original PDF, for citations."""
    if settings.storage_provider == 's3':
        safe_name = ''.join(c for c in title if c.isalnum() or c in ' ._-')[:120] or 'document.pdf'
        url = _s3().generate_presigned_url('get_object', ExpiresIn=DOWNLOAD_URL_TTL, Params={
            'Bucket': settings.document_bucket, 'Key': key,
            'ResponseContentType': 'application/pdf',
            'ResponseContentDisposition': f'inline; filename="{safe_name}"'})
        return {'url': url, 'requires_auth': False}
    return {'url': f'/api/documents/{document_id}/file', 'requires_auth': True}


def save_local(key: str, data: bytes) -> None:
    path = local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def read(key: str) -> bytes:
    if settings.storage_provider == 's3':
        return _s3().get_object(Bucket=settings.document_bucket, Key=key)['Body'].read()
    return local_path(key).read_bytes()


def delete(key: str) -> None:
    if settings.storage_provider == 's3':
        _s3().delete_object(Bucket=settings.document_bucket, Key=key)
    else:
        local_path(key).unlink(missing_ok=True)


def local_path(key: str) -> Path:
    base = Path(settings.local_upload_dir).resolve()
    path = (base / key).resolve()
    if not path.is_relative_to(base):
        raise ValueError('Invalid storage key')
    return path
