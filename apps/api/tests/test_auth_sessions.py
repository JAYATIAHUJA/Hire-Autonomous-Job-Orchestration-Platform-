"""Sessions, the get_current_user contract, CSRF, dev-login, logout and roles."""

import datetime

import pytest

from app.auth.deps import CSRF_HEADER
from app.auth.models import Account, Session
from app.auth.sessions import hash_token
from app.config import settings
from auth_helpers import app_db, create_account, login_as, logout, memory_client


@pytest.fixture
def client():
    with memory_client() as c:
        yield c


@pytest.fixture
def https_client():
    with memory_client("https://testserver") as c:
        yield c


def test_me_needs_a_session(client):
    assert client.get("/v1/me").status_code == 401


def test_login_as_makes_requests_authenticated(client):
    alice = create_account(client, "Alice@Example.com", display_name="Alice")
    login_as(client, alice)

    me = client.get("/v1/me").json()
    assert me["id"] == alice.id
    assert me["email"] == "alice@example.com"
    assert me["role"] == "user"
    assert me["providers"] == ["email"]


def test_only_the_token_hash_is_stored(client):
    token = login_as(client, create_account(client, "a@example.com"))
    with app_db(client) as db:
        stored = [row.token_hash for row in db.query(Session).all()]
    assert stored == [hash_token(token)]
    assert token not in stored


def test_unknown_expired_revoked_and_erased_sessions_are_rejected(client):
    account = create_account(client, "a@example.com")

    client.cookies.set(settings.session_cookie_name, "not-a-real-token")
    assert client.get("/v1/me").status_code == 401

    token = login_as(client, account)
    with app_db(client) as db:
        row = db.query(Session).filter_by(token_hash=hash_token(token)).one()
        row.expires_at = datetime.datetime(2000, 1, 1)
        db.commit()
    assert client.get("/v1/me").status_code == 401

    token = login_as(client, account)
    with app_db(client) as db:
        db.query(Session).filter_by(token_hash=hash_token(token)).one().revoked_at = datetime.datetime(2026, 1, 1)
        db.commit()
    assert client.get("/v1/me").status_code == 401

    login_as(client, account)
    assert client.get("/v1/me").status_code == 200
    with app_db(client) as db:
        db.get(Account, account.id).deleted_at = datetime.datetime(2026, 1, 1)
        db.commit()
    assert client.get("/v1/me").status_code == 401


def test_state_changing_cookie_requests_need_the_csrf_header(client):
    login_as(client, create_account(client, "a@example.com"))
    del client.headers[CSRF_HEADER]

    # Reads are fine without it; writes are refused even with a valid session.
    assert client.get("/api/applications/board").status_code == 200
    resp = client.post("/api/applications/swipe", json={"job_id": "blr_swig_001", "direction": "right"})
    assert resp.status_code == 403
    assert client.post("/v1/auth/logout").status_code == 403
    assert client.post("/v1/auth/otp/send", json={"email": "a@example.com"}).status_code == 403


def test_logout_revokes_the_session(https_client, monkeypatch):
    monkeypatch.setattr(settings, "env", "dev")
    https_client.headers[CSRF_HEADER] = "hire-web"
    https_client.post("/v1/auth/dev-login", json={"email": "a@example.com"})
    assert https_client.get("/v1/me").status_code == 200

    resp = https_client.post("/v1/auth/logout")
    assert resp.status_code == 204
    assert settings.session_cookie_name in resp.headers.get("set-cookie", "")
    with app_db(https_client) as db:
        assert all(row.revoked_at is not None for row in db.query(Session).all())
    assert https_client.get("/v1/me").status_code == 401


def test_dev_login_sets_a_hardened_cookie(https_client, monkeypatch):
    monkeypatch.setattr(settings, "env", "dev")
    https_client.headers[CSRF_HEADER] = "hire-web"

    resp = https_client.post("/v1/auth/dev-login", json={"email": "Dev@Example.com"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "dev@example.com"

    cookie = resp.headers["set-cookie"].lower()
    assert cookie.startswith(settings.session_cookie_name + "=")
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert https_client.get("/v1/me").json()["email"] == "dev@example.com"

    # Logging in again as the same email lands on the same account.
    again = https_client.post("/v1/auth/dev-login", json={"email": "dev@example.com"}).json()
    assert again["id"] == resp.json()["id"]


def test_a_new_login_retires_the_previous_session(https_client, monkeypatch):
    monkeypatch.setattr(settings, "env", "dev")
    https_client.headers[CSRF_HEADER] = "hire-web"
    https_client.post("/v1/auth/dev-login", json={"email": "a@example.com"})
    https_client.post("/v1/auth/dev-login", json={"email": "b@example.com"})
    with app_db(https_client) as db:
        live = [row for row in db.query(Session).all() if row.revoked_at is None]
    assert len(live) == 1


@pytest.mark.parametrize("env", ["prod", "production", "staging", ""])
def test_dev_login_does_not_exist_outside_dev(client, monkeypatch, env):
    monkeypatch.setattr(settings, "env", env)
    client.headers[CSRF_HEADER] = "hire-web"
    assert client.post("/v1/auth/dev-login", json={"email": "a@example.com"}).status_code == 404


def test_require_admin_gates_job_ingest(client):
    login_as(client, create_account(client, "user@example.com"))
    assert client.post("/jobs/ingest").status_code == 403

    login_as(client, create_account(client, "admin@example.com", role="admin"))
    resp = client.post("/jobs/ingest?limit=5")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_admin_emails_bootstrap_the_admin_role(https_client, monkeypatch):
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setattr(settings, "admin_emails", ["Boss@Example.com"])
    https_client.headers[CSRF_HEADER] = "hire-web"
    assert https_client.post("/v1/auth/dev-login", json={"email": "boss@example.com"}).json()["role"] == "admin"
    assert https_client.post("/v1/auth/dev-login", json={"email": "staff@example.com"}).json()["role"] == "user"


def test_logout_helper_drops_the_session(client):
    login_as(client, create_account(client, "a@example.com"))
    logout(client)
    assert client.get("/v1/me").status_code == 401
