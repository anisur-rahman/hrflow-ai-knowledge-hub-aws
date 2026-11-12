"""Authentication, authorization and configuration guards."""
import time
from types import SimpleNamespace

import jwt
import pytest
from conftest import approve, ask, upload
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import DEFAULT_API_KEY, Settings, settings
from app.security import auth


def test_api_key_required(client):
    assert client.get('/api/documents').status_code == 401
    assert client.get('/api/documents', headers={'X-API-Key': 'wrong'}).status_code == 401
    assert client.post('/api/chat', json={'question': 'hello there'}).status_code == 401


def test_employees_cannot_use_admin_endpoints(client, as_user):
    doc = upload(client)
    as_user('employee')
    assert client.post('/api/documents', json={'filename': 'a.pdf', 'size_bytes': 10}).status_code == 403
    assert client.patch(f'/api/documents/{doc["id"]}/review', json={'action': 'approve'}).status_code == 403
    assert client.post(f'/api/documents/{doc["id"]}/reprocess').status_code == 403
    assert client.delete(f'/api/documents/{doc["id"]}').status_code == 403
    assert client.get('/api/admin/stats').status_code == 403
    assert client.get('/api/admin/audit-events').status_code == 403


def test_unpublished_documents_are_hidden_from_employees(client, as_user):
    doc = upload(client)
    as_user('employee')
    assert client.get('/api/documents').json() == []
    assert client.get(f'/api/documents/{doc["id"]}').status_code == 404
    assert client.get(f'/api/documents/{doc["id"]}/source').status_code == 404


def test_restricted_document_is_invisible_to_other_groups(client, as_user):
    doc = upload(client, allowed_groups=['hr-admin'])
    approve(client, doc['id'])
    as_user('employee')
    assert client.get('/api/documents').json() == []
    assert client.get(f'/api/documents/{doc["id"]}').status_code == 404
    assert client.get(f'/api/documents/{doc["id"]}/source').status_code == 404
    assert client.get(f'/api/documents/{doc["id"]}/file').status_code == 404
    assert ask(client)['sources'] == []
    as_user('hr-admin')
    assert ask(client)['sources']


def test_user_without_groups_sees_nothing(client, as_user):
    doc = upload(client)
    approve(client, doc['id'])
    as_user()
    assert client.get('/api/documents').json() == [] and ask(client)['sources'] == []


def test_non_local_environment_requires_cognito():
    with pytest.raises(ValueError, match='AUTH_MODE=cognito'):
        Settings(environment='prod', auth_mode='apikey', _env_file=None)


def test_textract_requires_notification_channel():
    with pytest.raises(ValueError, match='TEXTRACT_SNS_TOPIC_ARN'):
        Settings(storage_provider='s3', document_bucket='b', ocr_provider='textract', _env_file=None)


def test_demo_key_is_only_offered_for_the_default_local_key(client, monkeypatch):
    assert client.get('/api/config').json()['demo_api_key'] is None  # tests use a custom key
    monkeypatch.setattr(settings, 'api_key', DEFAULT_API_KEY)
    assert client.get('/api/config').json()['demo_api_key'] == DEFAULT_API_KEY
    monkeypatch.setattr(settings, 'environment', 'dev')
    assert client.get('/api/config').json()['demo_api_key'] is None


def test_docs_disabled_outside_local(client):
    assert client.get('/docs').status_code == 200  # local test app


# ---------- Cognito access token verification ----------

@pytest.fixture
def cognito(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, 'cognito_user_pool_id', 'us-east-1_TEST')
    monkeypatch.setattr(settings, 'cognito_client_id', 'client-123')
    monkeypatch.setattr(auth, '_jwks_client', lambda: SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))

    def issue(signing_key=key, **overrides):
        now = int(time.time())
        claims = {'sub': 'user-1', 'username': 'jane', 'iss': settings.cognito_issuer, 'token_use': 'access',
                  'client_id': 'client-123', 'iat': now, 'exp': now + 300, 'cognito:groups': ['employee']}
        claims.update(overrides)
        return jwt.encode(claims, signing_key, algorithm='RS256')
    return issue


def test_valid_access_token(cognito):
    principal = auth.verify_cognito_access_token(cognito())
    assert principal.username == 'jane' and principal.groups == {'employee'} and not principal.is_admin


@pytest.mark.parametrize('overrides', [
    {'client_id': 'someone-else'},
    {'token_use': 'id'},
    {'exp': int(time.time()) - 3600},
    {'iss': 'https://evil.example.com'},
    {'signing_key': rsa.generate_private_key(public_exponent=65537, key_size=2048)},
], ids=['wrong-client', 'id-token', 'expired', 'wrong-issuer', 'forged-signature'])
def test_rejected_tokens(cognito, overrides):
    with pytest.raises(auth.InvalidToken):
        auth.verify_cognito_access_token(cognito(**overrides))


def test_bearer_token_flow_through_api(client, cognito, monkeypatch):
    monkeypatch.setattr(settings, 'auth_mode', 'cognito')
    assert client.get('/api/me').status_code == 401
    assert client.get('/api/me', headers={'Authorization': 'Bearer not-a-jwt'}).status_code == 401
    me = client.get('/api/me', headers={'Authorization': f'Bearer {cognito(**{"cognito:groups": ["hr-admin"]})}'})
    assert me.json() == {'username': 'jane', 'groups': ['hr-admin'], 'is_admin': True}
