"""Initial schema: documents with review workflow, chunks with pgvector HNSW index, audit events.

Revision ID: 0001
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table(
        'documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('version_label', sa.String(50)),
        sa.Column('storage_key', sa.String(255), nullable=False),
        sa.Column('size_bytes', sa.BigInteger),
        sa.Column('content_sha256', sa.String(64)),
        sa.Column('page_count', sa.Integer),
        sa.Column('chunk_count', sa.Integer),
        sa.Column('extraction_method', sa.String(20)),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('status_detail', sa.Text),
        sa.Column('attempts', sa.Integer, nullable=False, server_default='0'),
        sa.Column('ai_category', sa.String(80)),
        sa.Column('ai_summary', sa.Text),
        sa.Column('category', sa.String(80)),
        sa.Column('summary', sa.Text),
        sa.Column('allowed_groups', postgresql.ARRAY(sa.String(64)), nullable=False),
        sa.Column('uploaded_by', sa.String(128), nullable=False),
        sa.Column('reviewed_by', sa.String(128)),
        sa.Column('reviewed_at', TS),
        sa.Column('processed_at', TS),
        sa.Column('created_at', TS, nullable=False),
        sa.Column('updated_at', TS, nullable=False),
    )
    op.create_index('ix_documents_status', 'documents', ['status'])
    op.create_index('ix_documents_allowed_groups', 'documents', ['allowed_groups'], postgresql_using='gin')

    op.create_table(
        'chunks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('page', sa.Integer, nullable=False),
        sa.Column('position', sa.Integer, nullable=False),
        sa.Column('heading', sa.String(300)),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('embedding', Vector(1024), nullable=False),
        sa.UniqueConstraint('document_id', 'page', 'position'),
    )
    op.create_index('ix_chunks_document_id', 'chunks', ['document_id'])
    op.execute('CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)')

    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('actor', sa.String(128), nullable=False),
        sa.Column('action', sa.String(60), nullable=False),
        sa.Column('document_id', sa.String(36)),
        sa.Column('details', postgresql.JSONB, nullable=False),
        sa.Column('created_at', TS, nullable=False),
    )
    op.create_index('ix_audit_events_action', 'audit_events', ['action'])
    op.create_index('ix_audit_events_document_id', 'audit_events', ['document_id'])


def downgrade():
    op.drop_table('audit_events')
    op.drop_table('chunks')
    op.drop_table('documents')
