"""SQS batch handling shared by the Lambda workers (partial batch responses: one bad message is
retried and eventually dead-lettered without re-running the others)."""
import json
import logging
from collections.abc import Callable

from app.config import settings
from app.db import SessionLocal
from app.observability import configure_logging, log_event, request_id_var

configure_logging(settings.log_level)


def process_sqs_batch(event: dict, context, handle: Callable[[object, dict], None]) -> dict:
    request_id_var.set(getattr(context, 'aws_request_id', '-'))
    failures = []
    for record in event.get('Records', []):
        try:
            body = json.loads(record['body'])
            with SessionLocal() as db:
                handle(db, body)
        except Exception:
            log_event('worker.message_failed', level=logging.ERROR, exc_info=True, message_id=record.get('messageId'))
            failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': failures}
