"""Textract callback worker: Textract job completion (SNS -> SQS) -> finish_ocr.

No Lambda waits for OCR, so large scanned documents are not limited by the 15-minute Lambda timeout."""
import json

from app.services.ingestion import finish_ocr
from workers.common import process_sqs_batch


def textract_notification(body: dict) -> tuple[str, str] | None:
    """(JobId, Status) from a raw-delivery message or a standard SNS envelope."""
    if body.get('Type') == 'Notification' and isinstance(body.get('Message'), str):
        body = json.loads(body['Message'])
    if body.get('JobId') and body.get('Status'):
        return str(body['JobId']), str(body['Status'])
    return None


def _handle(db, body: dict) -> None:
    notification = textract_notification(body)
    if notification:
        finish_ocr(db, *notification)


def handler(event, context):
    return process_sqs_batch(event, context, _handle)
