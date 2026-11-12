"""Structured JSON logging. CloudWatch metric filters (see infrastructure/terraform/monitoring.tf)
turn `event` log lines into metrics, so the same code works locally, on ECS and on Lambda."""
import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str] = ContextVar('request_id', default='-')

_STANDARD_ATTRS = set(logging.LogRecord('', 0, '', 0, '', (), None).__dict__) | {'message', 'asctime', 'taskName'}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'ts': datetime.fromtimestamp(record.created, UTC).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'request_id': request_id_var.get(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = 'INFO') -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ('botocore', 'boto3', 'urllib3'):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def log_event(event: str, level: int = logging.INFO, exc_info: bool = False, **fields) -> None:
    logging.getLogger('hrflow.events').log(level, event, exc_info=exc_info, extra={'event': event, **fields})
