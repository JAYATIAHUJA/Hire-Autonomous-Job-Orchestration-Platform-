"""account_id foreign keys for the PoW and fact-vault tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-16 23:30:00.000000

WP2 (pow_runs, pow_evidence) and WP6 (candidate_profiles, profile_facts,
answer_bank, resume_uploads) were written before WP1's accounts table existed, so
their account_id had no FK. This adds one, matching the other owner-scoped tables.
Rows can only have been written by logged-in accounts, so there are no orphans.
"""

from alembic import op


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

TABLES = ("pow_runs", "pow_evidence", "candidate_profiles", "profile_facts", "answer_bank", "resume_uploads")


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.create_foreign_key(f"fk_{table}_account_id", "accounts", ["account_id"], ["id"])


def downgrade() -> None:
    for table in reversed(TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_account_id", type_="foreignkey")
