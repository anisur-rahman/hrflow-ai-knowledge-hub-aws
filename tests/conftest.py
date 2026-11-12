import os
import tempfile

# Configure the app for tests before anything imports app.config.
TEST_DATABASE_URL = os.environ.get('TEST_DATABASE_URL',
                                   'postgresql+psycopg://hrflow:hrflow_dev@localhost:5432/hrflow_test')
os.environ.update({
    'ENVIRONMENT': 'local', 'DATABASE_URL': TEST_DATABASE_URL, 'AI_PROVIDER': 'mock', 'AUTH_MODE': 'apikey',
    'API_KEY': 'test-key', 'API_KEY_GROUPS': 'hr-admin,employee', 'STORAGE_PROVIDER': 'local',
    'LOCAL_UPLOAD_DIR': tempfile.mkdtemp(prefix='hrflow-test-'), 'INGESTION_QUEUE_URL': '', 'OCR_PROVIDER': 'none',
})

from pathlib import Path  # noqa: E402

import pymupdf  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

ADMIN = {'X-API-Key': 'test-key'}


def make_pdf(pages: list[str], heading: str | None = None) -> bytes:
    doc = pymupdf.open()
    for body in pages:
        page = doc.new_page()
        y = 72
        if heading:
            page.insert_text((72, y), heading, fontsize=18)
            y += 30
        page.insert_textbox(pymupdf.Rect(72, y, 540, 760), body, fontsize=11)
    return doc.tobytes()


def _ensure_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    server = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
    with server.connect() as conn:
        exists = conn.execute(text('SELECT 1 FROM pg_database WHERE datname = :n'), {'n': url.database}).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    server.dispose()


@pytest.fixture(scope='session')
def database():
    try:
        _ensure_database()
    except OperationalError:
        pytest.skip('PostgreSQL with pgvector is not reachable (set TEST_DATABASE_URL)')
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[1]
    backend = root / 'backend' if (root / 'backend').is_dir() else root  # repo checkout vs test image
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'migrations'))
    command.upgrade(config, 'head')


@pytest.fixture
def client(database):
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.db import engine
    from app.main import app

    settings.ocr_provider = 'none'
    with engine.begin() as conn:
        conn.execute(text('TRUNCATE chunks, documents, audit_events CASCADE'))
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def as_user(client):
    """Switch the caller to a non-admin principal with the given groups."""
    from app.main import app
    from app.security import Principal, current_principal

    def switch(*groups: str):
        app.dependency_overrides[current_principal] = lambda: Principal('emp-1', 'employee1', frozenset(groups))
    return switch


POLICY = make_pdf([
    'Eligible employees may request reimbursement for approved home office equipment.',
    'The maximum annual home office equipment allowance is $500. Eligible purchases include an ergonomic desk '
    'chair, monitor and keyboard. Manager approval is required before purchase.',
    'Employees must submit itemized receipts within 30 calendar days of purchase.',
], heading='Remote Work Policy')


def upload(client, pdf=POLICY, filename='remote-work.pdf', **extra):
    """Two-step upload as the SPA does it; local mode processes in a background task."""
    created = client.post('/api/documents', headers=ADMIN, json={'filename': filename, 'size_bytes': len(pdf), **extra})
    assert created.status_code == 201, created.text
    target = created.json()['upload']
    assert target['requires_auth'] and target['fields'] == {}
    sent = client.post(target['url'], headers=ADMIN, files={'file': (filename, pdf, 'application/pdf')})
    assert sent.status_code == 202, sent.text
    return client.get(f'/api/documents/{created.json()["document"]["id"]}', headers=ADMIN).json()


def approve(client, doc_id, **changes):
    response = client.patch(f'/api/documents/{doc_id}/review', headers=ADMIN, json={'action': 'approve', **changes})
    assert response.status_code == 200, response.text
    return response.json()


def ask(client, question='Can I buy an ergonomic desk chair?', **extra):
    response = client.post('/api/chat', headers=ADMIN, json={'question': question, **extra})
    assert response.status_code == 200, response.text
    return response.json()
