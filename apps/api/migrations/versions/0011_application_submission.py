"""applications: whether the application was actually sent to the employer

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17 21:00:00

A right swipe records consent and puts the job on the board; it does not send anything.
submission_status says how far the actual application got: not_sent (the user still has
to apply), filling / needs_review (the auto-fill engine is working on it), sent, failed.
"""

from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('submission_status', sa.String(), nullable=False,
                                            server_default='not_sent'))
    op.add_column('applications', sa.Column('submitted_at', sa.DateTime(), nullable=True))
    op.add_column('applications', sa.Column('submit_method', sa.String(), nullable=True))
    # Cards already past "applied" were evidently sent.
    op.execute("UPDATE applications SET submission_status = 'sent', submit_method = 'self' "
               "WHERE stage IN ('interview_scheduled', 'rejected')")


def downgrade() -> None:
    for col in ('submit_method', 'submitted_at', 'submission_status'):
        op.drop_column('applications', col)
