"""Retrieval-augmented chat: grounding, citations, follow-ups, and the AI helpers' output parsing."""
import pytest
from conftest import ADMIN, approve, ask, upload

from app.services.classification import UNCATEGORIZED, parse_category
from app.services.embeddings import embed
from app.services.rag_service import NO_EVIDENCE, answer
from app.services.summarization import parse_summary


def test_only_published_documents_are_retrieved(client):
    doc = upload(client)
    assert ask(client)['answer'] == NO_EVIDENCE  # pending review: not even admins get answers from it
    approve(client, doc['id'])
    assert ask(client)['sources']


def test_answer_cites_title_version_page_and_section(client, as_user):
    doc = upload(client, version_label='2026.1')
    approve(client, doc['id'])
    as_user('employee')
    result = ask(client, 'Can I buy an ergonomic desk chair, and how much can I claim?')
    top = result['sources'][0]
    expected = ('remote-work.pdf', '2026.1', 2, 'Remote Work Policy')
    assert (top['title'], top['version'], top['page'], top['heading']) == expected
    assert '$500' in top['excerpt'] and 'ergonomic' in result['answer']
    link = client.get(f'/api/documents/{doc["id"]}/source').json()
    pdf = client.get(link['url'])
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF-')


def test_follow_up_uses_conversation_context(client):
    doc = upload(client)
    approve(client, doc['id'])
    result = ask(client, 'and what is the deadline?', history=[
        {'role': 'user', 'content': 'When must I submit receipts?'}, {'role': 'assistant', 'content': 'Within 30 days.'}])
    assert any(s['page'] == 3 for s in result['sources'])


def test_chat_history_must_alternate(client):
    bad = client.post('/api/chat', headers=ADMIN, json={'question': 'and monitors?',
                                                        'history': [{'role': 'assistant', 'content': 'hi'}]})
    assert bad.status_code == 422


def test_model_is_never_called_without_evidence(monkeypatch):
    monkeypatch.setattr('app.services.rag_service.converse', lambda *a, **k: pytest.fail('LLM called without evidence'))
    assert answer('anything?', [], []) == NO_EVIDENCE


def test_bedrock_prompt_contains_only_evidence_and_history(monkeypatch):
    seen = {}

    def fake_converse(system, messages, max_tokens, purpose):
        seen.update(system=system, messages=messages)
        return 'Yes (Policy, page 2)'
    monkeypatch.setattr('app.services.rag_service.settings.ai_provider', 'bedrock')
    monkeypatch.setattr('app.services.rag_service.converse', fake_converse)
    sources = [{'title': 'Policy "A"', 'version': '1', 'page': 2, 'heading': 'Equipment', 'content': 'Chairs: $500.'}]
    history = [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': 'hello'}]
    assert answer('Chairs?', sources, history) == 'Yes (Policy, page 2)'
    assert 'ONLY from the evidence' in seen['system']
    assert [m['role'] for m in seen['messages']] == ['user', 'assistant', 'user']
    final = seen['messages'][-1]['content'][0]['text']
    assert '<source title="Policy \'A\'" version="1" page="2" section="Equipment">' in final and final.endswith('Chairs?')


def test_embedding_dimension():
    assert len(embed('remote work reimbursement')) == 1024


@pytest.mark.parametrize('raw,expected', [
    ('{"category": "Finance/Operations"}', 'Finance/Operations'),
    ('Sure:\n{"category": "it"}\nThanks', 'IT'),
    ('{"category": "Benefits"}', UNCATEGORIZED),  # substring "it" must not match IT
    ('not json', UNCATEGORIZED),
    ('["a list"]', UNCATEGORIZED),
])
def test_parse_category(raw, expected):
    assert parse_category(raw) == expected


def test_parse_summary():
    assert parse_summary('{"summary": "Covers   home office\\nexpenses."}') == 'Covers home office expenses.'
    assert parse_summary('no json') == ''
