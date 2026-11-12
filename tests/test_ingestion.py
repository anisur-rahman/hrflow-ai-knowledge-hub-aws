"""Ingestion internals: chunking, headings, Lambda message parsing, and the async Textract flow."""
import json

import pytest
from conftest import ADMIN, make_pdf, upload

from app.config import settings
from app.services import extraction
from app.services.chunking import build_chunks, split_text
from app.services.extraction import PageText
from workers.ingest_lambda.handler import document_ids
from workers.ingest_lambda.handler import handler as ingest_handler
from workers.textract_callback.handler import handler as textract_handler
from workers.textract_callback.handler import textract_notification

SCANNED = make_pdf([''])  # a page with no selectable text


def test_chunking_hard_cut_without_whitespace():
    result = split_text('a' * 2500)
    assert len(result) == 3 and all(len(c) <= 1100 for c in result)


def test_chunking_prefers_word_boundaries():
    text = ' '.join(f'word{i}' for i in range(600))
    for chunk in split_text(text):
        words = chunk.split()
        assert words[0].startswith('word') and len(words[0]) >= 5 and len(words[-1]) >= 5


def test_empty_text_has_no_chunks():
    assert split_text('  ') == []


def test_headings_carry_over_pages():
    pages = [PageText(1, 'Equipment\nChairs are covered.', [(0, 'Equipment')]),
             PageText(2, 'Monitors are covered too.', [])]
    assert [(page, heading) for page, _, heading, _ in build_chunks(pages)] == [(1, 'Equipment'), (2, 'Equipment')]


def test_font_size_headings_are_detected():
    pages = extraction.extract_pages(make_pdf(['Body text about receipts.'], heading='Receipts'))
    assert pages[0].headings == [(0, 'Receipts')]


def test_ingest_message_parsing():
    doc_id = '0b8f8d4e-1111-4222-8333-944455556666'
    s3_event = {'Records': [{'s3': {'object': {'key': f'uploads/{doc_id}.pdf'}}},
                            {'s3': {'object': {'key': 'other/file.pdf'}}}]}
    assert document_ids(s3_event) == [doc_id]
    assert document_ids({'document_id': doc_id}) == [doc_id]
    assert document_ids({'Event': 's3:TestEvent'}) == []


def test_textract_notification_parsing():
    raw = {'JobId': 'job-1', 'Status': 'SUCCEEDED', 'API': 'StartDocumentTextDetection', 'JobTag': 'x'}
    assert textract_notification(raw) == ('job-1', 'SUCCEEDED')
    assert textract_notification({'Type': 'Notification', 'Message': json.dumps(raw)}) == ('job-1', 'SUCCEEDED')
    assert textract_notification({'unrelated': True}) is None


def test_scanned_pdf_without_ocr_fails_with_a_clear_reason(client):
    doc = upload(client, pdf=SCANNED)
    assert doc['status'] == 'failed' and 'OCR' in doc['status_detail']


@pytest.fixture
def fake_textract(monkeypatch):
    jobs = {}
    monkeypatch.setattr(settings, 'ocr_provider', 'textract')
    monkeypatch.setattr(extraction, 'start_textract',
                        lambda key, document_id: jobs.setdefault(document_id, f'job-{document_id[:8]}'))
    monkeypatch.setattr(extraction, 'textract_pages', lambda job_id: [
        PageText(1, '1. Equipment\nThe home office allowance is $500 per year.', [(0, '1. Equipment')])])
    return jobs


def sqs_event(*bodies):
    return {'Records': [{'messageId': f'm{i}', 'body': json.dumps(body)} for i, body in enumerate(bodies)]}


def test_scanned_pdf_goes_through_async_textract(client, fake_textract):
    doc = upload(client, pdf=SCANNED)
    assert doc['status'] == 'ocr_pending' and doc['extraction_method'] == 'textract'
    job_id = fake_textract[doc['id']]

    # A duplicate S3 event while OCR runs must not start a second job.
    assert ingest_handler(sqs_event({'document_id': doc['id']}), None) == {'batchItemFailures': []}
    assert len(fake_textract) == 1

    result = textract_handler(sqs_event({'Type': 'Notification', 'Message': json.dumps(
        {'JobId': job_id, 'Status': 'SUCCEEDED', 'API': 'StartDocumentTextDetection'})}), None)
    assert result == {'batchItemFailures': []}
    done = client.get(f'/api/documents/{doc["id"]}', headers=ADMIN).json()
    assert done['status'] == 'pending_review' and done['extraction_method'] == 'textract' and done['chunk_count'] == 1

    # Redelivered completion is ignored.
    assert textract_handler(sqs_event({'JobId': job_id, 'Status': 'SUCCEEDED'}), None) == {'batchItemFailures': []}


def test_failed_textract_job_marks_document_failed(client, fake_textract):
    doc = upload(client, pdf=SCANNED)
    textract_handler(sqs_event({'JobId': fake_textract[doc['id']], 'Status': 'FAILED'}), None)
    failed = client.get(f'/api/documents/{doc["id"]}', headers=ADMIN).json()
    assert failed['status'] == 'failed' and 'FAILED' in failed['status_detail']


def test_transient_callback_error_is_retried(client, fake_textract, monkeypatch):
    doc = upload(client, pdf=SCANNED)
    job_id = fake_textract[doc['id']]

    def boom(_):
        raise ConnectionError('Textract unavailable')
    monkeypatch.setattr(extraction, 'textract_pages', boom)
    assert textract_handler(sqs_event({'JobId': job_id, 'Status': 'SUCCEEDED'}), None) == {
        'batchItemFailures': [{'itemIdentifier': 'm0'}]}
    assert client.get(f'/api/documents/{doc["id"]}', headers=ADMIN).json()['status'] == 'ocr_pending'  # SQS retries it

    monkeypatch.setattr(extraction, 'textract_pages', lambda _: [PageText(1, 'Recovered text.', [])])
    textract_handler(sqs_event({'JobId': job_id, 'Status': 'SUCCEEDED'}), None)
    assert client.get(f'/api/documents/{doc["id"]}', headers=ADMIN).json()['status'] == 'pending_review'


def test_unknown_document_and_job_are_skipped(client):
    missing = '00000000-0000-4000-8000-000000000000'
    assert ingest_handler(sqs_event({'document_id': missing}), None)['batchItemFailures'] == []
    assert textract_handler(sqs_event({'JobId': 'nope', 'Status': 'SUCCEEDED'}), None)['batchItemFailures'] == []
