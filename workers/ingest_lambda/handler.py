"""Ingest worker: S3 ObjectCreated events (via SQS) and API reprocess requests -> start_ingestion.

Digital PDFs are fully processed here. Scanned PDFs start an asynchronous Textract job and this
invocation ends; workers/textract_callback finishes them when Textract reports completion."""
import re
from urllib.parse import unquote_plus

from app.services.ingestion import start_ingestion
from workers.common import process_sqs_batch

_UPLOAD_KEY = re.compile(r'uploads/([0-9a-f-]{36})\.pdf')


def document_ids(body: dict) -> list[str]:
    if 'document_id' in body:  # reprocess request from the API
        return [str(body['document_id'])]
    ids = []
    for record in body.get('Records', []):  # S3 event notification; s3:TestEvent has no Records
        match = _UPLOAD_KEY.fullmatch(unquote_plus(record.get('s3', {}).get('object', {}).get('key', '')))
        if match:
            ids.append(match.group(1))
    return ids


def _handle(db, body: dict) -> None:
    for document_id in document_ids(body):
        start_ingestion(db, document_id)


def handler(event, context):
    return process_sqs_batch(event, context, _handle)
