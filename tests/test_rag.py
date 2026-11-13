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


# ---------- Bedrock Converse request (what the app sends to AWS) ----------

class FakeBedrock:
    def __init__(self, stop_reason='end_turn'):
        self.calls, self.stop_reason = [], stop_reason

    def converse(self, **request):
        self.calls.append(request)
        return {'output': {'message': {'content': [{'reasoningContent': {'reasoningText': {'text': 'hidden'}}},
                                                   {'text': 'Answer.'}]}},
                'usage': {'inputTokens': 10, 'outputTokens': 5}, 'stopReason': self.stop_reason}


@pytest.fixture
def fake_bedrock(monkeypatch):
    from app.services import bedrock
    fake = FakeBedrock()
    monkeypatch.setattr(bedrock, 'client', lambda: fake)
    monkeypatch.setattr(bedrock.settings, 'bedrock_chat_model_id', 'test-model')
    return fake


def test_converse_sends_no_sampling_parameters_by_default(fake_bedrock):
    from app.services.bedrock import converse
    assert converse('sys', [{'role': 'user', 'content': [{'text': 'hi'}]}], 4096, purpose='answer') == 'Answer.'
    request = fake_bedrock.calls[0]
    assert request['inferenceConfig'] == {'maxTokens': 4096}  # no temperature: current Claude models reject it
    assert 'additionalModelRequestFields' not in request
    assert request['modelId'] == 'test-model' and request['system'] == [{'text': 'sys'}]


def test_converse_optional_effort_and_temperature(fake_bedrock, monkeypatch):
    from app.services.bedrock import converse, settings
    monkeypatch.setattr(settings, 'bedrock_effort', 'low')
    monkeypatch.setattr(settings, 'bedrock_temperature', 0.2)
    converse('sys', [{'role': 'user', 'content': [{'text': 'hi'}]}], 1024, purpose='classification')
    request = fake_bedrock.calls[0]
    assert request['additionalModelRequestFields'] == {'output_config': {'effort': 'low'}}
    assert request['inferenceConfig'] == {'maxTokens': 1024, 'temperature': 0.2}


def test_ai_calls_leave_room_for_thinking(fake_bedrock, monkeypatch):
    from app.services import classification, rag_service, summarization
    for module in (classification, summarization, rag_service):
        monkeypatch.setattr(module.settings, 'ai_provider', 'bedrock')
    classification.classify('policy text')
    summarization.summarize('policy text')
    rag_service.answer('q?', [{'title': 'T', 'version': None, 'page': 1, 'heading': None, 'content': 'c'}], [])
    assert [c['inferenceConfig']['maxTokens'] for c in fake_bedrock.calls] == [1024, 2048, 4096]
