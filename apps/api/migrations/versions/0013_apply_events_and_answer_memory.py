"""apply run events (live progress) and remembered form answers (answer memory)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-17 23:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'apply_run_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('apply_runs.id'), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('field_name', sa.String(), nullable=True),
        sa.Column('shown_value', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('run_id', 'seq', name='uq_apply_run_events_run_seq'),
    )
    op.create_index('ix_apply_run_events_run_id', 'apply_run_events', ['run_id'])

    op.create_table(
        'answer_memory',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('question_norm', sa.String(), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('uses', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('account_id', 'question_norm', name='uq_answer_memory_account_question'),
    )
    op.create_index('ix_answer_memory_account_id', 'answer_memory', ['account_id'])


def downgrade() -> None:
    op.drop_table('answer_memory')
    op.drop_table('apply_run_events')
