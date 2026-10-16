"""privacy consents and onboarding completion

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-16 23:45:00.000000

privacy_consents is the append-only record of which DPDP notice (version and
sha256 of its text) each account accepted, with one switch per purpose.
accounts.onboarding_completed_at lets the web route guard skip the wizard.
"""

from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'privacy_consents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('notice_version', sa.String(length=32), nullable=False),
        sa.Column('notice_hash', sa.String(length=64), nullable=False),
        sa.Column('purposes', sa.JSON(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=False),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name='fk_privacy_consents_account_id'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('privacy_consents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_privacy_consents_account_id'), ['account_id'], unique=False)

    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('onboarding_completed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_column('onboarding_completed_at')

    with op.batch_alter_table('privacy_consents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_privacy_consents_account_id'))
    op.drop_table('privacy_consents')
