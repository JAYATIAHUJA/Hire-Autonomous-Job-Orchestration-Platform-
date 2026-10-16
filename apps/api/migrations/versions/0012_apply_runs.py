"""apply runs: Hire filling an employer's application form, with the user reviewing it

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-17 23:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')
    op.create_table(
        'apply_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('application_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('step', sa.String(), nullable=True),
        sa.Column('filled', json_type, nullable=False),
        sa.Column('missing', json_type, nullable=False),
        sa.Column('extra_answers', json_type, nullable=False),
        sa.Column('screenshot_key', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_apply_runs_account_id', 'apply_runs', ['account_id'])
    op.create_index('ix_apply_runs_application_id', 'apply_runs', ['application_id'])
    op.create_index('ix_apply_runs_status', 'apply_runs', ['status'])


def downgrade() -> None:
    op.drop_table('apply_runs')
