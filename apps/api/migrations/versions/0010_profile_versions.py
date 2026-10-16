"""profile versions: targeted cuts of the master profile ("Backend", "Data", ...)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17 18:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')
    op.create_table(
        'profile_versions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('headline', sa.String(), nullable=True),
        sa.Column('target_role', sa.String(), nullable=True),
        sa.Column('fact_ids', json_type, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_profile_versions_account_id', 'profile_versions', ['account_id'])


def downgrade() -> None:
    op.drop_index('ix_profile_versions_account_id', table_name='profile_versions')
    op.drop_table('profile_versions')
