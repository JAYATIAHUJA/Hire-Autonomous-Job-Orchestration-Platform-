"""DPDP consent, onboarding and preferences on /v1/me, and the consent gates on collection."""

import hashlib

import pytest

from auth_helpers import create_account, login_as, memory_client

pytestmark = pytest.mark.enforce_consent

NOTICE_HASH = hashlib.sha256(b"How Hire uses your personal data\nVersion v1\n\n...").hexdigest()


def consent(**purposes):
    return {"notice_version": "v1", "notice_hash": NOTICE_HASH,
            "purposes": {"github": False, "resume": False, "email": False, **purposes}}


@pytest.fixture
def client():
    with memory_client() as c:
        c.alice = create_account(c, "alice@example.com")
        c.bob = create_account(c, "bob@example.com")
        login_as(c, c.alice)
        yield c


def test_new_account_has_no_consent_and_has_not_onboarded(client):
    me = client.get("/v1/me").json()
    assert me["consent"] is None and me["onboarding_completed_at"] is None
    assert me["identities"] == me["providers"] == ["email"]


def test_consent_is_recorded_and_returned_on_me(client):
    resp = client.post("/v1/me/consents", json=consent(github=True))
    assert resp.status_code == 201, resp.text
    assert resp.json()["purposes"] == {"github": True, "resume": False, "email": False}
    me = client.get("/v1/me").json()
    assert me["consent"]["notice_hash"] == NOTICE_HASH
    assert me["consent"]["purposes"]["github"] is True


def test_a_change_of_mind_is_a_new_record_and_wins(client):
    client.post("/v1/me/consents", json=consent(github=True, resume=True))
    client.post("/v1/me/consents", json=consent(github=True))
    assert client.get("/v1/me").json()["consent"]["purposes"] == {"github": True, "resume": False, "email": False}


def test_consent_to_an_old_or_malformed_notice_is_refused(client):
    assert client.post("/v1/me/consents", json={**consent(), "notice_version": "v0"}).status_code == 422
    assert client.post("/v1/me/consents", json={**consent(), "notice_hash": "not-a-hash"}).status_code == 422


def test_consent_belongs_to_the_logged_in_account(client):
    client.post("/v1/me/consents", json=consent(github=True))
    login_as(client, client.bob)
    assert client.get("/v1/me").json()["consent"] is None


def test_onboarding_completes_once(client):
    first = client.patch("/v1/me", json={"onboarding_completed": True}).json()["onboarding_completed_at"]
    assert first
    again = client.patch("/v1/me", json={"onboarding_completed": True}).json()["onboarding_completed_at"]
    assert again == first
    assert client.patch("/v1/me", json={"onboarding_completed": False}).status_code == 422


def test_preferences_round_trip_and_merge(client):
    prefs = {"roles": ["Backend Engineer", " "], "locations": ["Bengaluru"], "remote_ok": True,
             "experience_band": "1-3", "salary_floor": {"amount": 1800000, "currency": "INR", "period": "year"},
             "deal_breakers": ["unpaid trial"]}
    saved = client.patch("/v1/me/preferences", json=prefs)
    assert saved.status_code == 200, saved.text
    assert saved.json()["roles"] == ["Backend Engineer"]
    client.patch("/v1/me/preferences", json={"remote_ok": False})
    got = client.get("/v1/me/preferences").json()
    assert got["remote_ok"] is False and got["locations"] == ["Bengaluru"]
    assert client.patch("/v1/me/preferences", json={"experience_band": "99"}).status_code == 422

    login_as(client, client.bob)
    assert client.get("/v1/me/preferences").json()["roles"] == []


def test_preferences_survive_a_profile_rebuild(client):
    from app.facts import repository
    from auth_helpers import app_db

    client.patch("/v1/me/preferences", json={"roles": ["SRE"]})
    with app_db(client) as db:
        repository.refresh_profile(db, client.alice.id)
        db.commit()
    assert client.get("/v1/me/preferences").json()["roles"] == ["SRE"]


def test_github_analysis_needs_github_consent(client):
    refused = client.post("/v1/profile/pow/refresh", json={"github_username": "priyadev"})
    assert refused.status_code == 403
    assert "GitHub" in refused.json()["detail"]
    assert client.post("/api/profile/analyze", json={"username": "priyadev"}).status_code == 403

    client.post("/v1/me/consents", json=consent(github=True))
    queued = client.post("/v1/profile/pow/refresh", json={"github_username": "priyadev"})
    assert queued.status_code == 202, queued.text


def test_withdrawing_consent_closes_the_gate_again(client):
    client.post("/v1/me/consents", json=consent(github=True))
    client.post("/v1/me/consents", json=consent())
    assert client.post("/v1/profile/pow/refresh", json={"github_username": "priyadev"}).status_code == 403


def test_resume_parsing_needs_resume_consent(client):
    files = {"file": ("resume.pdf", b"%PDF-1.4 tiny", "application/pdf")}
    assert client.post("/v1/profile/resume", files=files).status_code == 403
    client.post("/v1/me/consents", json=consent(resume=True))
    # Past the gate: whatever happens next (storage, parsing) is not a consent refusal.
    assert client.post("/v1/profile/resume", files=files).status_code != 403


def test_pow_refresh_accepts_an_empty_body_when_github_is_linked(client):
    from app.services import github_tokens

    client.post("/v1/me/consents", json=consent(github=True))
    github_tokens.set_linked_login_provider(lambda db, account_id: "priyadev")
    try:
        resp = client.post("/v1/profile/pow/refresh")
        assert resp.status_code == 202, resp.text
        assert resp.json()["github_username"] == "priyadev"
    finally:
        github_tokens.set_linked_login_provider(None)
