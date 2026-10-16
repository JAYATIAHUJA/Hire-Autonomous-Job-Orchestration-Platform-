"""fact vault: profile facts, candidate profiles, answer bank, resume uploads

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16 17:07:04.239190

Follows WP1 (0003) and WP2 (0004). account_id has no FK to accounts yet; a
follow-up migration adds it.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    op.create_table('answer_bank',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'key', name='uq_answer_bank_account_key')
    )
    op.create_index(op.f('ix_answer_bank_account_id'), 'answer_bank', ['account_id'], unique=False)

    op.create_table('candidate_profiles',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('data', JSON, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_candidate_profiles_account_id'), 'candidate_profiles', ['account_id'], unique=True)

    op.create_table('profile_facts',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('structured', JSON, nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('source_ref', sa.String(), nullable=True),
    sa.Column('inferred', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('conflict_with_fact_id', sa.String(), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['conflict_with_fact_id'], ['profile_facts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_profile_facts_account_id'), 'profile_facts', ['account_id'], unique=False)
    op.create_index(op.f('ix_profile_facts_kind'), 'profile_facts', ['kind'], unique=False)
    op.create_index(op.f('ix_profile_facts_status'), 'profile_facts', ['status'], unique=False)

    op.create_table('resume_uploads',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('object_key', sa.String(), nullable=False),
    sa.Column('sha256', sa.String(), nullable=False),
    sa.Column('content_type', sa.String(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('text_source', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resume_uploads_account_id'), 'resume_uploads', ['account_id'], unique=False)
    op.create_index(op.f('ix_resume_uploads_sha256'), 'resume_uploads', ['sha256'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_resume_uploads_sha256'), table_name='resume_uploads')
    op.drop_index(op.f('ix_resume_uploads_account_id'), table_name='resume_uploads')
    op.drop_table('resume_uploads')
    op.drop_index(op.f('ix_profile_facts_status'), table_name='profile_facts')
    op.drop_index(op.f('ix_profile_facts_kind'), table_name='profile_facts')
    op.drop_index(op.f('ix_profile_facts_account_id'), table_name='profile_facts')
    op.drop_table('profile_facts')
    op.drop_index(op.f('ix_candidate_profiles_account_id'), table_name='candidate_profiles')
    op.drop_table('candidate_profiles')
    op.drop_index(op.f('ix_answer_bank_account_id'), table_name='answer_bank')
    op.drop_table('answer_bank')
