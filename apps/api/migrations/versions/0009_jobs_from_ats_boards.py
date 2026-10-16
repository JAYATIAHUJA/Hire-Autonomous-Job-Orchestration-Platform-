"""jobs: where each job came from, its original posting, and discovery runs

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17 12:00:00

Jobs now come from real employer boards (Greenhouse, Lever, Ashby) and RemoteOK, so
each row records its source, the posting to apply on, when it was posted and when a
board last listed it. The hard-coded demo jobs from Phase 0 are marked as samples.
"""

from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('source', sa.String(), nullable=True))
    op.add_column('jobs', sa.Column('apply_url', sa.String(), nullable=True))
    op.add_column('jobs', sa.Column('posted_at', sa.DateTime(), nullable=True))
    op.add_column('jobs', sa.Column('last_seen_at', sa.DateTime(), nullable=True))
    op.add_column('jobs', sa.Column('is_remote', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('ix_jobs_source', 'jobs', ['source'])
    op.execute("UPDATE jobs SET source = 'sample' WHERE source IS NULL")
    op.add_column('companies', sa.Column('jobs_fetched_at', sa.DateTime(), nullable=True))
    op.create_table(
        'discovery_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('status', sa.String(), nullable=False),  # requested | running | done | failed
        sa.Column('requested_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('boards_checked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('boards_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('jobs_added', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('jobs_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('jobs_closed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ghosts_filtered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.Text(), nullable=True),
    )
    op.create_index('ix_discovery_runs_status', 'discovery_runs', ['status'])


def downgrade() -> None:
    op.drop_index('ix_discovery_runs_status', table_name='discovery_runs')
    op.drop_table('discovery_runs')
    op.drop_column('companies', 'jobs_fetched_at')
    op.drop_index('ix_jobs_source', table_name='jobs')
    for col in ('is_remote', 'last_seen_at', 'posted_at', 'apply_url', 'source'):
        op.drop_column('jobs', col)
