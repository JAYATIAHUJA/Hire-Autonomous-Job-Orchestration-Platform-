"""Owner scoping (T13): every route needs a session, and user B can never read or change
user A's rows. Another account's row answers 404, not 403, so existence never leaks."""

import re

import pytest
from fastapi.routing import APIRoute

from app import models as pow_models
from app.auth.deps import CSRF_HEADER
from app.config import settings
from app.main import app
from auth_helpers import app_db, create_account, login_as, memory_client

PUBLIC_PATHS = {"/health"}
PUBLIC_PREFIXES = ("/v1/auth/",)
REJECTION = "We regret to inform you that we have decided to move forward with other candidates."


@pytest.fixture
def client():
    with memory_client() as c:
        c.alice = create_account(c, "alice@example.com")
        c.bob = create_account(c, "bob@example.com")
        yield c


def _private_routes():
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in PUBLIC_PATHS or route.path.startswith(PUBLIC_PREFIXES):
            continue
        for method in route.methods:
            yield method, route.path


PRIVATE_ROUTES = sorted(set(_private_routes()))


def test_there_are_private_routes_to_check():
    paths = {path for _, path in PRIVATE_ROUTES}
    assert {"/api/applications/deck", "/api/mail/sync", "/api/profile/{profile_id}", "/jobs/feed", "/v1/me"} <= paths


@pytest.mark.parametrize("method, path", PRIVATE_ROUTES)
def test_every_private_route_needs_a_session(method, path):
    with memory_client() as anonymous:
        url = re.sub(r"\{[^}]+\}", "1", path)
        resp = anonymous.request(method, url, json={}, headers={CSRF_HEADER: "hire-web"})
        assert resp.status_code == 401, f"{method} {path} answered {resp.status_code} without a session"


def _alice_applies(client, job_id="blr_swig_001") -> str:
    login_as(client, client.alice)
    client.get("/api/applications/deck")
    resp = client.post("/api/applications/swipe", json={"job_id": job_id, "direction": "right"})
    assert resp.status_code == 200
    return resp.json()["application"]["application_id"]


def test_bob_cannot_read_alices_application_or_receipt(client):
    app_id = _alice_applies(client)
    assert client.get(f"/api/applications/{app_id}").status_code == 200

    login_as(client, client.bob)
    for url in (f"/api/applications/{app_id}", f"/api/applications/{app_id}/consent"):
        resp = client.get(url)
        # Same answer as for an id that never existed.
        fake_id = "app_0000000000000000"
        missing = client.get(url.replace(app_id, fake_id))
        assert resp.status_code == missing.status_code == 404
        assert resp.json()["detail"].replace(app_id, fake_id) == missing.json()["detail"]


def test_bob_cannot_move_alices_card(client):
    app_id = _alice_applies(client)

    login_as(client, client.bob)
    resp = client.post(f"/api/applications/{app_id}/stage", json={"to_stage": "rejected"})
    assert resp.status_code == 404
    # A bad stage on someone else's card is still a 404: no validation oracle.
    assert client.post(f"/api/applications/{app_id}/stage", json={"to_stage": "nope"}).status_code == 404

    login_as(client, client.alice)
    assert client.get(f"/api/applications/{app_id}").json()["stage"] == "applied"


def test_board_and_deck_are_per_account(client):
    _alice_applies(client)
    alice_board = client.get("/api/applications/board").json()
    assert alice_board["total"] == 1
    assert alice_board["candidate_ref"] == f"account:{client.alice.id}"

    login_as(client, client.bob)
    # Asking for Alice by name changes nothing.
    board = client.get(f"/api/applications/board?candidate_ref=account:{client.alice.id}").json()
    assert board["total"] == 0 and board["candidate_ref"] == f"account:{client.bob.id}"
    deck = client.get("/api/applications/deck?candidate_ref=alice@example.com").json()
    assert "blr_swig_001" in {job["job_id"] for job in deck["jobs"]}


def test_swiping_the_same_job_gives_each_account_its_own_card_and_receipt(client):
    alice_app = _alice_applies(client)

    login_as(client, client.bob)
    client.get("/api/applications/deck")
    bob = client.post(
        "/api/applications/swipe",
        json={"job_id": "blr_swig_001", "direction": "right", "candidate_ref": "alice@example.com"},
    ).json()
    assert bob["already_recorded"] is False
    assert bob["application"]["application_id"] != alice_app
    assert bob["consent"]["subject"] == f"account:{client.bob.id}"


def test_bobs_mail_cannot_move_alices_card(client):
    app_id = _alice_applies(client)

    login_as(client, client.bob)
    stats = client.post(
        "/api/mail/sync",
        json={"messages": [{"uid": "1", "from_address": "careers@swiggy.com", "subject": "Update", "body": REJECTION},
                           {"uid": "2", "from_address": "x@y.io", "subject": f"Re: {app_id}", "body": REJECTION}]},
    ).json()
    assert stats["moved"] == 0

    login_as(client, client.alice)
    assert client.get(f"/api/applications/{app_id}").json()["stage"] == "applied"


def test_only_the_mailbox_owner_may_read_the_server_mailbox(client, monkeypatch):
    monkeypatch.setattr(settings, "imap_candidate_ref", "alice@example.com")

    login_as(client, client.bob)
    assert client.post("/api/mail/sync", json={}).status_code == 404

    # Alice gets past the owner check; with no IMAP host configured the read itself is a 503.
    login_as(client, client.alice)
    resp = client.post("/api/mail/sync", json={})
    assert resp.status_code == 503 and "IMAP_HOST" in resp.json()["detail"]


def test_mailbox_owner_resolves_by_id_or_email(client, monkeypatch):
    from app.mail.sync import mailbox_account_id

    with app_db(client) as db:
        for ref, expected in (
            (str(client.alice.id), client.alice.id),
            (f"account:{client.bob.id}", client.bob.id),
            ("BOB@example.com", client.bob.id),
            ("nobody@example.com", None),
            ("", None),
        ):
            monkeypatch.setattr(settings, "imap_candidate_ref", ref)
            assert mailbox_account_id(db) == expected, ref


def test_bob_cannot_read_alices_pow_profile(client):
    with app_db(client) as db:
        mine = pow_models.User(username="alice-gh", analysis_mode="limited", account_id=client.alice.id)
        legacy = pow_models.User(username="old-run", analysis_mode="limited", account_id=None)
        db.add_all([mine, legacy])
        db.commit()
        mine_id, legacy_id = mine.id, legacy.id

    login_as(client, client.alice)
    assert client.get(f"/api/profile/{mine_id}").status_code == 200
    # Rows from before WP1 belong to nobody until a GitHub login claims them.
    assert client.get(f"/api/profile/{legacy_id}").status_code == 404

    login_as(client, client.bob)
    assert client.get(f"/api/profile/{mine_id}").status_code == 404


def test_me_only_ever_shows_the_caller(client):
    login_as(client, client.bob)
    me = client.get("/v1/me").json()
    assert me["id"] == client.bob.id and me["email"] == "bob@example.com"
