"""accounts, auth identities, sessions, OTP codes; owner-scope personal rows

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16 17:10:49.992606

Data path for rows written before WP1, when the owner was the free-text
``applications.candidate_ref``: each distinct ref becomes one account (with that
ref as its email when it looks like one, so an OTP or verified-email login claims
it later), and its applications, consent receipts and mail-ledger rows get that
account's id. Ledger keys move from "<ref>|<key>" to "account:<id>|<key>" so mail
already applied is not applied twice.
"""

import datetime
import re

import sqlalchemy as sa
from alembic import op


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _backfill_owners() -> None:
    bind = op.get_bind()
    accounts = sa.Table(
        "accounts",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String),
        sa.Column("display_name", sa.String),
        sa.Column("role", sa.String),
        sa.Column("created_at", sa.DateTime),
    )
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    refs = [r[0] for r in bind.execute(sa.text("SELECT DISTINCT candidate_ref FROM applications"))]
    by_ref: dict[str, int] = {}
    by_email: dict[str, int] = {}
    for ref in sorted(refs):
        cleaned = (ref or "").strip().lower()
        email = cleaned if EMAIL_RE.match(cleaned) else None
        if email and email in by_email:
            by_ref[ref] = by_email[email]
            continue
        result = bind.execute(
            accounts.insert().values(email=email, display_name=ref, role="user", created_at=now)
        )
        account_id = result.inserted_primary_key[0]
        by_ref[ref] = account_id
        if email:
            by_email[email] = account_id

    for ref, account_id in by_ref.items():
        bind.execute(
            sa.text("UPDATE applications SET account_id = :aid WHERE candidate_ref = :ref"),
            {"aid": account_id, "ref": ref},
        )
    bind.execute(
        sa.text(
            "UPDATE consent_logs SET account_id = "
            "(SELECT a.account_id FROM applications a WHERE a.id = consent_logs.application_db_id)"
        )
    )

    rows = bind.execute(sa.text("SELECT message_uid FROM processed_messages")).fetchall()
    for (uid,) in rows:
        prefix, sep, rest = (uid or "").partition("|")
        if sep and prefix in by_ref:
            bind.execute(
                sa.text("UPDATE processed_messages SET account_id = :aid, message_uid = :new WHERE message_uid = :old"),
                {"aid": by_ref[prefix], "new": f"account:{by_ref[prefix]}|{rest}", "old": uid},
            )


def upgrade() -> None:
    op.create_table('accounts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('display_name', sa.String(), nullable=True),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("role IN ('user', 'admin', 'support')", name='ck_accounts_role'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('otp_codes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('ip', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('consumed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('otp_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_otp_codes_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_otp_codes_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_otp_codes_ip'), ['ip'], unique=False)

    op.create_table('auth_identities',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('subject', sa.String(), nullable=False),
    sa.Column('username', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('access_token_encrypted', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("provider IN ('github', 'google', 'email')", name='ck_auth_identities_provider'),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name='fk_auth_identities_account_id'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'subject', name='uq_auth_identities_provider_subject')
    )
    with op.batch_alter_table('auth_identities', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auth_identities_account_id'), ['account_id'], unique=False)

    op.create_table('sessions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('user_agent', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name='fk_sessions_account_id'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sessions_account_id'), ['account_id'], unique=False)

    # Owner columns start nullable so existing rows can be backfilled first.
    for table in ('applications', 'consent_logs', 'processed_messages', 'users'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('account_id', sa.Integer(), nullable=True))

    _backfill_owners()

    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.alter_column('account_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(batch_op.f('ix_applications_account_id'), ['account_id'], unique=False)
        batch_op.create_unique_constraint('uq_application_account_job', ['account_id', 'job_id'])
        batch_op.create_foreign_key('fk_applications_account_id', 'accounts', ['account_id'], ['id'])

    with op.batch_alter_table('consent_logs', schema=None) as batch_op:
        batch_op.alter_column('account_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(batch_op.f('ix_consent_logs_account_id'), ['account_id'], unique=False)
        batch_op.create_foreign_key('fk_consent_logs_account_id', 'accounts', ['account_id'], ['id'])

    with op.batch_alter_table('processed_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_processed_messages_account_id'), ['account_id'], unique=False)
        batch_op.create_foreign_key('fk_processed_messages_account_id', 'accounts', ['account_id'], ['id'])

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_account_id'), ['account_id'], unique=False)
        batch_op.create_foreign_key('fk_users_account_id', 'accounts', ['account_id'], ['id'])


def downgrade() -> None:
    # Lossy by design: ledger keys stay in their "account:<id>|..." form.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_account_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_users_account_id'))
        batch_op.drop_column('account_id')

    with op.batch_alter_table('processed_messages', schema=None) as batch_op:
        batch_op.drop_constraint('fk_processed_messages_account_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_processed_messages_account_id'))
        batch_op.drop_column('account_id')

    with op.batch_alter_table('consent_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_consent_logs_account_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_consent_logs_account_id'))
        batch_op.drop_column('account_id')

    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.drop_constraint('fk_applications_account_id', type_='foreignkey')
        batch_op.drop_constraint('uq_application_account_job', type_='unique')
        batch_op.drop_index(batch_op.f('ix_applications_account_id'))
        batch_op.drop_column('account_id')

    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sessions_account_id'))

    op.drop_table('sessions')
    with op.batch_alter_table('auth_identities', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auth_identities_account_id'))

    op.drop_table('auth_identities')
    with op.batch_alter_table('otp_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_otp_codes_ip'))
        batch_op.drop_index(batch_op.f('ix_otp_codes_email'))
        batch_op.drop_index(batch_op.f('ix_otp_codes_created_at'))

    op.drop_table('otp_codes')
    op.drop_table('accounts')
