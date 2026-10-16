"""companies: public ATS board from the registry

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16 16:10:00

0006 is WP3's reserved id. 0003-0005 belong to other work packages; whichever
merges later rebases its down_revision onto the head at that time.
"""

from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('ats_vendor', sa.String(), nullable=True))
    op.add_column('companies', sa.Column('ats_board_token', sa.String(), nullable=True))
    op.add_column('companies', sa.Column('ats_checked_at', sa.DateTime(), nullable=True))
    op.create_index('ix_companies_ats_board', 'companies', ['ats_vendor', 'ats_board_token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_companies_ats_board', table_name='companies')
    op.drop_column('companies', 'ats_checked_at')
    op.drop_column('companies', 'ats_board_token')
    op.drop_column('companies', 'ats_vendor')
