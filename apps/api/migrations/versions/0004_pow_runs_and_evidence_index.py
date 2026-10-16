"""pow runs and evidence index

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-16 17:15:19.273542

WP2. Follows WP1's accounts migration (0003). account_id has no FK to accounts
yet; a follow-up migration adds it.
"""

from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

ACTIVE = sa.text("status IN ('queued', 'running')")


def upgrade() -> None:
    op.create_table('pow_runs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('github_username', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('progress', sa.Integer(), nullable=False),
    sa.Column('include_private', sa.Boolean(), nullable=False),
    sa.Column('token_source', sa.String(), nullable=True),
    sa.Column('sample_coverage', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('profile_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['profile_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pow_runs_account_id'), 'pow_runs', ['account_id'], unique=False)
    op.create_index(op.f('ix_pow_runs_status'), 'pow_runs', ['status'], unique=False)
    # One queued/running run per account.
    op.create_index('uq_pow_runs_one_active_per_account', 'pow_runs', ['account_id'], unique=True,
                    postgresql_where=ACTIVE, sqlite_where=ACTIVE)

    op.create_table('pow_evidence',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('skill', sa.String(), nullable=False),
    sa.Column('skill_key', sa.String(), nullable=False),
    sa.Column('repo', sa.String(), nullable=False),
    sa.Column('url', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.Column('date', sa.DateTime(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('is_private', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['pow_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pow_evidence_account_id'), 'pow_evidence', ['account_id'], unique=False)
    op.create_index('ix_pow_evidence_account_skill', 'pow_evidence', ['account_id', 'skill_key'], unique=False)
    op.create_index(op.f('ix_pow_evidence_run_id'), 'pow_evidence', ['run_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pow_evidence_run_id'), table_name='pow_evidence')
    op.drop_index('ix_pow_evidence_account_skill', table_name='pow_evidence')
    op.drop_index(op.f('ix_pow_evidence_account_id'), table_name='pow_evidence')
    op.drop_table('pow_evidence')
    op.drop_index('uq_pow_runs_one_active_per_account', table_name='pow_runs')
    op.drop_index(op.f('ix_pow_runs_status'), table_name='pow_runs')
    op.drop_index(op.f('ix_pow_runs_account_id'), table_name='pow_runs')
    op.drop_table('pow_runs')
