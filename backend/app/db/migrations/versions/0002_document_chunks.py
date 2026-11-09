"""document_chunks lexical storage

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# PostgreSQL-only full-text expression index. The SQLite test/dev dialect
# uses an FTS5 mirror table created at runtime instead (see
# app/services/rag/lexical.py), so this statement must never run there.
POSTGRES_TSV_INDEX = (
    "CREATE INDEX ix_document_chunks_tsv ON document_chunks "
    "USING GIN (to_tsvector('simple', text))"
)


def upgrade() -> None:
    op.create_table(
        'document_chunks',
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('collection_id', sa.Uuid(), nullable=True),
        sa.Column('chunk_id', sa.String(length=64), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('page', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=400), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['collection_id'], ['collections.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('document_chunks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_document_chunks_chunk_id'), ['chunk_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_document_chunks_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_document_chunks_tenant_collection', ['tenant_id', 'collection_id'], unique=False)
        batch_op.create_index('ix_document_chunks_tenant_document', ['tenant_id', 'document_id'], unique=False)

    if op.get_bind().dialect.name == 'postgresql':
        op.execute(POSTGRES_TSV_INDEX)


def downgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_tsv")

    with op.batch_alter_table('document_chunks', schema=None) as batch_op:
        batch_op.drop_index('ix_document_chunks_tenant_document')
        batch_op.drop_index('ix_document_chunks_tenant_collection')
        batch_op.drop_index(batch_op.f('ix_document_chunks_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_document_chunks_chunk_id'))

    op.drop_table('document_chunks')
