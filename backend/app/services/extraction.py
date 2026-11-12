"""Text extraction: PyMuPDF for digital PDFs (with heading detection), asynchronous Textract for scans."""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

import boto3
import pymupdf

from app.config import settings

_NUMBERED_HEADING = re.compile(r'^(?:\d+(?:\.\d+)*[.)]?|[A-Z][.)]|section \d+|article \d+|page \d+:)\s+\S', re.IGNORECASE)


class IngestionError(Exception):
    """A permanent problem with the document itself; retrying will not help."""


@dataclass
class PageText:
    number: int
    text: str
    headings: list[tuple[int, str]] = field(default_factory=list)  # (character offset, heading text)


def has_text(pages: list[PageText]) -> bool:
    return any(page.text.strip() for page in pages)


def extract_pages(data: bytes) -> list[PageText]:
    if not data.startswith(b'%PDF-'):
        raise IngestionError('File is not a PDF')
    try:
        pdf = pymupdf.open(stream=data, filetype='pdf')
    except Exception as exc:
        raise IngestionError('PDF could not be parsed') from exc
    with pdf:
        if pdf.needs_pass:
            raise IngestionError('Password-protected PDFs are not supported')
        if pdf.page_count > settings.max_pages:
            raise IngestionError(f'PDF has {pdf.page_count} pages; the limit is {settings.max_pages}')
        styled = [(index + 1, _styled_lines(page)) for index, page in enumerate(pdf)]
    body_size = _body_font_size(line for _, lines in styled for line in lines)
    return [_assemble(number, lines, body_size) for number, lines in styled]


def _styled_lines(page) -> list[tuple[str, float, bool]]:
    lines = []
    for block in page.get_text('dict')['blocks']:
        if block.get('type') != 0:
            continue
        for line in block['lines']:
            spans = [s for s in line['spans'] if s['text'].strip()]
            if spans:
                text = ' '.join(s['text'].strip() for s in spans)
                lines.append((text, max(s['size'] for s in spans), all(s['flags'] & 16 for s in spans)))
    return lines


def _body_font_size(lines) -> float:
    weights = Counter()
    for text, size, _ in lines:
        weights[round(size, 1)] += len(text)
    return weights.most_common(1)[0][0] if weights else 0.0


def _looks_like_heading(text: str, size: float, bold: bool, body_size: float) -> bool:
    if len(text) > 120 or not any(c.isalpha() for c in text) or text.endswith(('.', ',', ';')):
        return False
    if body_size > 0 and (size >= body_size * 1.15 or (bold and size >= body_size)):
        return True
    return bool(_NUMBERED_HEADING.match(text)) and len(text) <= 80


def _assemble(number: int, lines: list[tuple[str, float, bool]], body_size: float) -> PageText:
    parts, headings, offset = [], [], 0
    for text, size, bold in lines:
        if _looks_like_heading(text, size, bold, body_size):
            headings.append((offset, text[:300]))
        parts.append(text)
        offset += len(text) + 1
    return PageText(number, '\n'.join(parts), headings)


# ---------- Textract (asynchronous) ----------

@lru_cache
def _textract():
    return boto3.client('textract', region_name=settings.aws_region)


def start_textract(key: str, document_id: str) -> str:
    """Starts OCR and returns immediately. Textract publishes completion to SNS -> SQS ->
    the textract_callback worker, so no Lambda waits on the job."""
    response = _textract().start_document_text_detection(
        DocumentLocation={'S3Object': {'Bucket': settings.document_bucket, 'Name': key}},
        NotificationChannel={'SNSTopicArn': settings.textract_sns_topic_arn, 'RoleArn': settings.textract_role_arn},
        JobTag=document_id,
        ClientRequestToken=document_id,  # idempotent if the start is retried
    )
    return response['JobId']


def textract_pages(job_id: str) -> list[PageText]:
    """Collects the LINE blocks of a finished job, page by page (results are paginated)."""
    lines: dict[int, list[str]] = defaultdict(list)
    token = None
    while True:
        kwargs = {'JobId': job_id, 'MaxResults': 1000, **({'NextToken': token} if token else {})}
        result = _textract().get_document_text_detection(**kwargs)
        for block in result.get('Blocks', []):
            if block['BlockType'] == 'LINE':
                lines[block['Page']].append(block['Text'])
        token = result.get('NextToken')
        if not token:
            break
    return [_assemble(page, [(text, 0.0, False) for text in lines[page]], 0.0) for page in sorted(lines)]
