"""Track the Textract job of documents waiting for asynchronous OCR.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('documents', sa.Column('textract_job_id', sa.String(128)))
    op.create_index('ix_documents_textract_job_id', 'documents', ['textract_job_id'])


def downgrade():
    op.drop_index('ix_documents_textract_job_id', 'documents')
    op.drop_column('documents', 'textract_job_id')
