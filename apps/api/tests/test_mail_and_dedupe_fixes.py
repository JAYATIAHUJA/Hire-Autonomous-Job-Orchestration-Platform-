"""Regression tests for B5, B7 and B9 (PLAN.md §1.1), fixed after Phase 0."""

import asyncio
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.applications import models as application_models  # noqa: F401
from app.db import Base, get_db
from app.jobs import models as job_models
from app.jobs.ingestion.canonical_key import cross_portal_key, normalize_location
from app.jobs.pipeline import process_and_ingest_job_items
from app.mail import imap_client
from app.mail.imap_client import ImapConfig, fetch_recruiter_messages, message_key
from app.mail.sync import match_application
from app.main import app

ALICE = "alice"
BOB = "bob"


@pytest.fixture
def session_and_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    yield Session, TestClient(app)
    app.dependency_overrides.clear()


def _apply(client, candidate: str, job_id: str) -> str:
    client.get(f"/api/applications/deck?candidate_ref={candidate}")
    resp = client.post(
        "/api/applications/swipe",
        json={"job_id": job_id, "direction": "right", "candidate_ref": candidate},
    )
    return resp.json()["application"]["application_id"]


def _sync(client, candidate: str, *messages: dict) -> dict:
    return client.post("/api/mail/sync", json={"candidate_ref": candidate, "messages": list(messages)}).json()


def _stage(client, application_id: str) -> str:
    return client.get(f"/api/applications/{application_id}").json()["stage"]


REJECTION = "We regret to inform you that we have decided to move forward with other candidates."


# --- B5: IMAP ids ---------------------------------------------------------------

def _raw(subject: str, message_id: str | None) -> bytes:
    msg = EmailMessage()
    msg["From"] = "careers@swiggy.com"
    msg["Subject"] = subject
    if message_id:
        msg["Message-ID"] = message_id
    msg.set_content("Please share your availability for an interview.")
    return msg.as_bytes()


class _FakeImap:
    """Records the commands used; serves UIDs that differ from sequence numbers."""

    calls: list[tuple] = []

    def __init__(self, host, port):
        self.calls.clear()

    def login(self, user, password):
        pass

    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        return "OK", [b"2"]

    def response(self, code):
        return code, [b"777"] if code == "UIDVALIDITY" else [None]

    def search(self, *args):  # sequence-number search must not be used
        raise AssertionError("plain SEARCH returns sequence numbers, not UIDs")

    def fetch(self, *args):
        raise AssertionError("plain FETCH takes sequence numbers, not UIDs")

    def uid(self, command, *args):
        self.calls.append(("uid", command) + args)
        if command == "SEARCH":
            return "OK", [b"501 502"]
        uid = args[0]
        mid = "<abc-123@mail.swiggy.com>" if uid == b"501" else None
        return "OK", [(b"501 (RFC822 {100}", _raw(f"Interview {uid.decode()}", mid))]

    def logout(self):
        pass


def test_b5_fetch_uses_uid_commands_and_stable_keys(monkeypatch):
    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", _FakeImap)
    cfg = ImapConfig(host="imap.example", port=993, username="u", password="p")

    messages = fetch_recruiter_messages(cfg, limit=10)

    assert [c[1] for c in _FakeImap.calls if c[0] == "uid"] == ["SEARCH", "FETCH", "FETCH"]
    assert [m["uid"] for m in messages] == ["501", "502"]
    # Message-ID wins; without one the key is scoped to mailbox + UIDVALIDITY.
    assert messages[0]["message_key"] == "msgid:abc-123@mail.swiggy.com"
    assert messages[1]["message_key"] == "imap:INBOX:777:502"


def test_b5_a_uidvalidity_reset_does_not_collide_with_old_ids():
    before = message_key(None, mailbox="INBOX", uidvalidity="777", uid="5")
    after = message_key(None, mailbox="INBOX", uidvalidity="778", uid="5")
    assert before != after


def test_b5_the_same_message_id_is_processed_once_even_with_new_uids(session_and_client):
    _, client = session_and_client
    application_id = _apply(client, ALICE, "blr_swig_001")
    msg = {"from_address": "careers@swiggy.com", "subject": "Your application", "body": REJECTION}

    first = _sync(client, ALICE, {**msg, "uid": "10", "message_id": "<same@swiggy.com>"})
    # The server renumbered the mailbox; the message is the same.
    second = _sync(client, ALICE, {**msg, "uid": "99", "message_id": "<SAME@swiggy.com>"})

    assert first["moved"] == 1
    assert second["skipped"] == 1 and second["moved"] == 0
    assert _stage(client, application_id) == "rejected"


# --- B7: mail matching scope ---------------------------------------------------

def test_b7_a_reply_only_moves_the_mailbox_owners_card(session_and_client):
    _, client = session_and_client
    alice_app = _apply(client, ALICE, "blr_swig_001")
    bob_app = _apply(client, BOB, "blr_swig_001")

    stats = _sync(
        client, BOB,
        {"uid": "1", "from_address": "careers@swiggy.com", "subject": "Update", "body": REJECTION},
    )

    assert stats["moved"] == 1
    assert _stage(client, bob_app) == "rejected"
    assert _stage(client, alice_app) == "applied"


def test_b7_inline_sync_requires_a_candidate(session_and_client):
    _, client = session_and_client
    resp = client.post(
        "/api/mail/sync",
        json={"messages": [{"uid": "1", "from_address": "x@y.com", "subject": "s", "body": REJECTION}]},
    )
    assert resp.status_code == 422


def test_b7_rejected_cards_do_not_absorb_matches(session_and_client):
    _, client = session_and_client
    cred_app = _apply(client, ALICE, "pune_cred_003")
    client.post(f"/api/applications/{cred_app}/stage", json={"to_stage": "rejected"})

    stats = _sync(
        client, ALICE,
        {"uid": "2", "from_address": "hiring@cred.club", "subject": "Interview invitation",
         "body": "We would like to invite you to a technical interview. Please share your availability."},
    )

    assert stats["matched"] == 0
    assert _stage(client, cred_app) == "rejected"


class _App:
    def __init__(self, application_id, employer_name, employer_domain=None):
        self.application_id = application_id
        self.employer_name = employer_name
        self.employer_domain = employer_domain


def test_b7_employer_names_match_whole_words_only():
    cred = _App("app_00000001", "CRED")
    msg = {"from_address": "noreply@jobs-portal.io", "subject": "An incredible opportunity", "body": REJECTION}
    assert match_application(msg, [cred]) == (None, "no matching card")

    msg["subject"] = "Your CRED application"
    assert match_application(msg, [cred])[0] is cred


def test_b7_equally_good_employer_matches_are_left_alone():
    a = _App("app_00000001", "Acme Analytics")
    b = _App("app_00000002", "Acme Robotics")
    msg = {"from_address": "noreply@portal.io", "subject": "Acme update", "body": REJECTION}
    assert match_application(msg, [a, b]) == (None, "ambiguous employer name")


# --- B9: cross-portal dedupe ---------------------------------------------------

def test_b9_the_same_job_on_two_boards_has_one_key():
    greenhouse = cross_portal_key("Swiggy", "Backend Engineer", "Bengaluru, Karnataka, India")
    linkedin = cross_portal_key("Swiggy Technologies Pvt Ltd", "Backend Engineer", "Bangalore")
    assert greenhouse == linkedin
    assert cross_portal_key("Swiggy", "Frontend Engineer", "Bengaluru") != greenhouse
    assert cross_portal_key("Swiggy", "Backend Engineer", "Hyderabad") != greenhouse


@pytest.mark.parametrize(
    "raw, expected",
    [("Bengaluru, KA (Hybrid)", "bengaluru"), ("Bangalore", "bengaluru"), ("Gurgaon, Haryana", "gurugram"),
     ("Remote (India)", "remote"), ("", "")],
)
def test_b9_locations_normalise(raw, expected):
    assert normalize_location(raw) == expected


def test_b9_pipeline_keeps_one_copy_across_sources(session_and_client):
    Session, _ = session_and_client
    base = {
        "title": "Backend Engineer",
        "posting_age_days": 3,
        "repost_count": 0,
        "salary_range": "10-15 LPA",
        "raw_description": "Build Python and PostgreSQL services with FastAPI. Requirements: Python, SQL.",
    }
    items = [
        {**base, "source_id": "greenhouse_1", "company_name": "Swiggy", "location": "Bengaluru, India"},
        {**base, "source_id": "linkedin_9", "company_name": "Swiggy Technologies", "location": "Bangalore"},
    ]

    db = Session()
    try:
        stats = asyncio.run(process_and_ingest_job_items(db, items))
        assert stats["duplicate_count"] == 1
        assert [j.job_id for j in db.query(job_models.Job).all()] == ["greenhouse_1"]

        # Re-ingesting the first source updates it rather than counting as a duplicate.
        again = asyncio.run(process_and_ingest_job_items(db, items[:1]))
        assert again["duplicate_count"] == 0
    finally:
        db.close()
