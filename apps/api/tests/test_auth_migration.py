"""Migration 0003 moves pre-WP1 rows from the free-text candidate_ref onto accounts."""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.config import settings

API_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def alembic_db(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)  # migrations/env.py reads it
    # No ini file: env.py then skips fileConfig, which would disable the app's loggers
    # for every test that runs after this one.
    cfg = Config()
    cfg.set_main_option("script_location", str(API_ROOT / "migrations"))
    return cfg, sa.create_engine(url)


def test_legacy_rows_get_owner_accounts(alembic_db):
    cfg, engine = alembic_db
    command.upgrade(cfg, "0002")
    with engine.begin() as conn:
        for row_id, ref, job in ((1, "oshisharma1222", "j1"), (2, "Ana@Example.com", "j1"), (3, "ana@example.com", "j2")):
            conn.execute(
                sa.text(
                    "INSERT INTO applications (id, application_id, candidate_ref, job_id, employer_name, "
                    "role_title, stage, swipe_direction) VALUES (:id, :aid, :ref, :job, 'Swiggy', 'BE', 'applied', 'right')"
                ),
                {"id": row_id, "aid": f"app_{row_id}", "ref": ref, "job": job},
            )
        conn.execute(sa.text(
            "INSERT INTO consent_logs (consent_id, application_db_id, subject, employer_name, purpose, granted_at, "
            "payload_json, signature, algorithm) VALUES ('c1', 1, 'oshisharma1222', 'Swiggy', 'p', 't', '{}', 's', 'HMAC-SHA256')"
        ))
        conn.execute(sa.text(
            "INSERT INTO processed_messages (message_uid, classification) VALUES "
            "('oshisharma1222|msgid:x@y', 'rejected'), ('unscoped-uid', 'none')"
        ))

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        accounts = conn.execute(sa.text("SELECT id, email, display_name FROM accounts ORDER BY id")).fetchall()
        owners = dict(conn.execute(sa.text("SELECT application_id, account_id FROM applications")).fetchall())
        consent_owner = conn.execute(sa.text("SELECT account_id FROM consent_logs")).scalar_one()
        ledger = dict(conn.execute(sa.text("SELECT message_uid, account_id FROM processed_messages")).fetchall())

    by_name = {name: (acc_id, email) for acc_id, email, name in accounts}
    # Two spellings of one email collapse into one account; a handle gets one without an email.
    assert len(accounts) == 2
    ana_id, ana_email = by_name["Ana@Example.com"]
    oshi_id, oshi_email = by_name["oshisharma1222"]
    assert ana_email == "ana@example.com" and oshi_email is None
    assert owners == {"app_1": oshi_id, "app_2": ana_id, "app_3": ana_id}
    assert consent_owner == oshi_id
    # Ledger keys move to the account form so already-applied mail stays applied.
    assert ledger == {f"account:{oshi_id}|msgid:x@y": oshi_id, "unscoped-uid": None}

    command.downgrade(cfg, "0002")
    command.upgrade(cfg, "head")
