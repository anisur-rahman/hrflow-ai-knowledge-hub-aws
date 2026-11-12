"""Document lifecycle: upload, processing, HR review and publishing, admin operations."""
from conftest import ADMIN, POLICY, approve, upload


def test_health_and_public_config(client):
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.get('/health/ready').json() == {'status': 'ready'}
    config = client.get('/api/config').json()
    assert config['auth_mode'] == 'apikey' and 'Finance/Operations' in config['categories']


def test_upload_is_processed_into_pending_review(client):
    doc = upload(client, version_label='2026.1')
    assert doc['status'] == 'pending_review', doc
    assert doc['category'] == doc['ai_category'] == 'Finance/Operations'
    assert doc['summary'] == doc['ai_summary'] and doc['summary']
    assert doc['page_count'] == 3 and doc['chunk_count'] >= 3 and doc['extraction_method'] == 'text'
    assert doc['size_bytes'] == len(POLICY)


def test_review_edits_are_saved_and_audited(client):
    doc = upload(client)
    published = approve(client, doc['id'], summary='Home office equipment and receipts.', category='IT',
                        version_label='2026.2', allowed_groups=['employee', 'managers'])
    assert published['status'] == 'published' and published['reviewed_by'] == 'local-demo'
    assert published['category'] == 'IT' and published['ai_category'] == 'Finance/Operations'
    assert published['allowed_groups'] == ['employee', 'managers'] and published['version_label'] == '2026.2'
    events = client.get('/api/admin/audit-events', headers=ADMIN, params={'document_id': doc['id']}).json()
    approved = next(e for e in events if e['action'] == 'document.approved')
    assert approved['details']['ai_summary_edited'] and approved['details']['ai_category_overridden']


def test_upload_validation(client):
    assert client.post('/api/documents', headers=ADMIN, json={'filename': 'a.docx', 'size_bytes': 10}).status_code == 422
    too_big = client.post('/api/documents', headers=ADMIN, json={'filename': 'a.pdf', 'size_bytes': 50 * 1024 * 1024})
    assert too_big.status_code == 413
    created = client.post('/api/documents', headers=ADMIN, json={'filename': 'a.pdf', 'size_bytes': 10}).json()
    not_pdf = client.post(created['upload']['url'], headers=ADMIN, files={'file': ('a.pdf', b'hello', 'application/pdf')})
    assert not_pdf.status_code == 400
    again = client.post(created['upload']['url'], headers=ADMIN, files={'file': ('a.pdf', POLICY, 'application/pdf')})
    assert again.status_code == 202
    twice = client.post(created['upload']['url'], headers=ADMIN, files={'file': ('a.pdf', POLICY, 'application/pdf')})
    assert twice.status_code == 409


def test_unparseable_pdf_is_marked_failed_and_can_be_reprocessed(client):
    doc = upload(client, pdf=b'%PDF-1.7 this is not really a pdf')
    assert doc['status'] == 'failed' and doc['status_detail']
    assert client.post(f'/api/documents/{doc["id"]}/reprocess', headers=ADMIN).status_code == 202
    assert client.get(f'/api/documents/{doc["id"]}', headers=ADMIN).json()['status'] == 'failed'


def test_review_rules(client):
    created = client.post('/api/documents', headers=ADMIN, json={'filename': 'a.pdf', 'size_bytes': 10}).json()
    doc_id = created['document']['id']
    assert client.patch(f'/api/documents/{doc_id}/review', headers=ADMIN, json={'action': 'approve'}).status_code == 409
    assert client.post(f'/api/documents/{doc_id}/reprocess', headers=ADMIN).status_code == 409  # still uploading
    doc = upload(client)
    blank = client.patch(f'/api/documents/{doc["id"]}/review', headers=ADMIN, json={'action': 'approve', 'summary': ' '})
    assert blank.status_code == 422
    rejected = client.patch(f'/api/documents/{doc["id"]}/review', headers=ADMIN, json={'action': 'reject'})
    assert rejected.json()['status'] == 'rejected'


def test_reprocessing_a_published_document_returns_it_to_review(client):
    doc = upload(client)
    approve(client, doc['id'])
    client.post(f'/api/documents/{doc["id"]}/reprocess', headers=ADMIN)
    assert client.get(f'/api/documents/{doc["id"]}', headers=ADMIN).json()['status'] == 'pending_review'


def test_delete_removes_document_and_file(client):
    doc = upload(client)
    approve(client, doc['id'])
    assert client.delete(f'/api/documents/{doc["id"]}', headers=ADMIN).status_code == 204
    assert client.get(f'/api/documents/{doc["id"]}', headers=ADMIN).status_code == 404
    assert client.get('/api/admin/stats', headers=ADMIN).json()['searchable_chunks'] == 0


def test_dashboard_stats(client):
    doc = upload(client)
    upload(client)
    approve(client, doc['id'])
    client.post('/api/chat', headers=ADMIN, json={'question': 'ergonomic desk chair allowance'})
    client.post('/api/chat', headers=ADMIN, json={'question': 'parental leave weeks'})
    stats = client.get('/api/admin/stats', headers=ADMIN).json()
    assert stats['documents_by_status'] == {'published': 1, 'pending_review': 1}
    assert stats['searchable_chunks'] >= 3
    assert stats['questions_7d'] == 2 and stats['unanswered_7d'] == 1


def test_review_accepts_exactly_the_classifier_categories(client):
    from app.services.classification import CATEGORIES, UNCATEGORIZED

    doc = upload(client)
    for category in (*CATEGORIES, UNCATEGORIZED):
        assert approve(client, doc['id'], category=category)['category'] == category
    bogus = client.patch(f'/api/documents/{doc["id"]}/review', headers=ADMIN,
                         json={'action': 'approve', 'category': 'Benefits'})
    assert bogus.status_code == 422
