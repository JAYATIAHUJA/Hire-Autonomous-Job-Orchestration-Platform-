"""DELETE /v1/me: DPDP erasure removes the account and everything it owns, and only that."""

import hashlib

import pytest

from app import models as pow_profile_models
from app.applications.models import Application, ConsentLog, PipelineEvent, ProcessedMessage
from app.auth.models import Account, AuthIdentity, PrivacyConsent, Session
from app.facts.models import AnswerBankEntry, CandidateProfile, ProfileFact, ResumeUpload
from app.facts.storage import get_object_store
from app.main import app
from app.profiles.pow_models import PowEvidence, PowRun
from auth_helpers import app_db, create_account, login_as, memory_client

REJECTION = "We regret to inform you that we have decided to move forward with other candidates."
CONSENT = {"notice_version": "v1", "notice_hash": hashlib.sha256(b"notice").hexdigest(),
           "purposes": {"github": True, "resume": True, "email": False}}
OWNED = (PrivacyConsent, AuthIdentity, Session, Application, ConsentLog, ProcessedMessage, PowRun, PowEvidence,
         CandidateProfile, ProfileFact, AnswerBankEntry, ResumeUpload, pow_profile_models.User)


class FakeStore:
    def __init__(self):
        self.deleted: list[str] = []

    def delete(self, key: str) -> None:
        self.deleted.append(key)


@pytest.fixture
def client():
    with memory_client() as c:
        c.alice = create_account(c, "alice@example.com")
        c.bob = create_account(c, "bob@example.com")
        c.store = FakeStore()
        app.dependency_overrides[get_object_store] = lambda: c.store
        yield c
        app.dependency_overrides.pop(get_object_store, None)


def fill(client, account) -> None:
    """Give the account a row in every table that holds personal data."""
    login_as(client, account)
    assert client.post("/v1/me/consents", json=CONSENT).status_code == 201
    client.patch("/v1/me/preferences", json={"roles": ["SRE"]})
    client.put("/v1/me/answer-bank", json={"answers": {"notice_period": "30 days"}})
    client.get("/api/applications/deck")
    swipe = client.post("/api/applications/swipe", json={"job_id": "blr_swig_001", "direction": "right"})
    assert swipe.status_code == 200, swipe.text
    client.post("/api/mail/sync", json={"messages": [
        {"uid": f"u-{account.id}", "from_address": "careers@swiggy.com", "subject": "Update", "body": REJECTION}]})
    assert client.post("/v1/profile/pow/refresh", json={"github_username": f"gh{account.id}"}).status_code == 202
    with app_db(client) as db:
        run = db.query(PowRun).filter(PowRun.account_id == account.id).one()
        db.add(PowEvidence(account_id=account.id, run_id=run.id, skill="Python", skill_key="python",
                           repo="r/r", url="https://github.com/r/r", kind="repo", weight=1.0, summary="repo"))
        db.add(pow_profile_models.User(username=f"gh{account.id}", analysis_mode="limited", account_id=account.id))
        upload = ResumeUpload(account_id=account.id, object_key=f"resumes/{account.id}.pdf", sha256="0" * 64,
                              content_type="application/pdf", size_bytes=10, text_source="text_layer")
        db.add(upload)
        db.flush()
        db.add(ProfileFact(account_id=account.id, kind="skill", text="Python", structured={}, source="resume",
                           source_ref=upload.id, status="proposed"))
        db.commit()


def counts(client, account_id: int) -> dict[str, int]:
    with app_db(client) as db:
        out = {model.__tablename__: db.query(model).filter(model.account_id == account_id).count() for model in OWNED}
        out["pipeline_events"] = db.query(PipelineEvent).join(Application).filter(
            Application.account_id == account_id).count()
        out["accounts"] = db.query(Account).filter(Account.id == account_id).count()
        return out


def test_delete_me_erases_everything_alice_owns_and_nothing_of_bobs(client):
    fill(client, client.alice)
    fill(client, client.bob)
    before = counts(client, client.alice.id)
    assert all(before.values()), before  # the fixture really touched every table

    login_as(client, client.alice)
    resp = client.delete("/v1/me")
    assert resp.status_code == 204, resp.text
    assert "hire_session" in resp.headers.get("set-cookie", "")

    assert not any(counts(client, client.alice.id).values()), counts(client, client.alice.id)
    assert all(counts(client, client.bob.id).values())
    assert client.store.deleted == [f"resumes/{client.alice.id}.pdf"]

    # The old session is gone with the account.
    assert client.get("/v1/me").status_code == 401


def test_erasure_without_storage_deletes_nothing_when_files_exist(client):
    fill(client, client.alice)
    app.dependency_overrides[get_object_store] = lambda: None
    login_as(client, client.alice)
    assert client.delete("/v1/me").status_code == 503
    assert all(counts(client, client.alice.id).values())


def test_delete_me_needs_the_csrf_header(client):
    login_as(client, client.alice)
    client.headers.pop("X-Requested-With")
    assert client.delete("/v1/me").status_code == 403
    assert counts(client, client.alice.id)["accounts"] == 1
