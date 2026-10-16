"""GitHub and Google OAuth with the providers mocked by httpx.MockTransport (no network)."""

import datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet

from app import models as pow_models
from app.auth import oauth
from app.auth.crypto import decrypt_token
from app.auth.models import Account, AuthIdentity
from app.auth.tokens import get_github_token
from app.config import settings
from auth_helpers import app_db, create_account, login_as, memory_client

GITHUB_USER = {"id": 4242, "login": "ana-dev", "name": "Ana Dev", "email": None}
GITHUB_EMAILS = [
    {"email": "old@example.com", "primary": False, "verified": True},
    {"email": "ana@example.com", "primary": True, "verified": True},
]
GOOGLE_INFO = {"sub": "g-777", "email": "ana@example.com", "email_verified": True, "name": "Ana G"}


class Providers:
    """Fake GitHub + Google endpoints. Records requests; responses can be swapped per test."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.github_user = dict(GITHUB_USER)
        self.github_emails = list(GITHUB_EMAILS)
        self.google_info = dict(GOOGLE_INFO)
        self.reject_code = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url == oauth.GITHUB_TOKEN_URL:
            if self.reject_code:
                return httpx.Response(200, json={"error": "bad_verification_code"})
            return httpx.Response(200, json={"access_token": "gho_secret_token", "token_type": "bearer"})
        if url.endswith("/user") and "api.github.com" in url:
            return httpx.Response(200, json=self.github_user)
        if url.endswith("/user/emails"):
            return httpx.Response(200, json=self.github_emails)
        if url == oauth.GOOGLE_TOKEN_URL:
            if self.reject_code:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "ya29.google", "id_token": "x"})
        if url == oauth.GOOGLE_USERINFO_URL:
            return httpx.Response(200, json=self.google_info)
        return httpx.Response(404, json={})


@pytest.fixture
def providers(monkeypatch):
    fake = Providers()
    monkeypatch.setattr(oauth, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    monkeypatch.setattr(settings, "github_oauth_client_id", "gh-client")
    monkeypatch.setattr(settings, "github_oauth_client_secret", "gh-secret")
    monkeypatch.setattr(settings, "google_oauth_client_id", "g-client")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "g-secret")
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "github_api_base", "https://api.github.com")
    monkeypatch.setattr(settings, "auth_callback_base_url", "https://api.hire.test")
    monkeypatch.setattr(settings, "web_app_url", "https://app.hire.test")
    return fake


@pytest.fixture
def client(providers):
    with memory_client("https://testserver") as c:
        yield c


def _login(client, provider="github", code="the-code"):
    start = client.get(f"/v1/auth/{provider}/start", follow_redirects=False)
    assert start.status_code == 302
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return client.get(f"/v1/auth/{provider}/callback?code={code}&state={state}", follow_redirects=False)


def test_github_start_redirects_with_state_and_minimal_scopes(client):
    resp = client.get("/v1/auth/github/start", follow_redirects=False)
    assert resp.status_code == 302
    location = urlparse(resp.headers["location"])
    query = parse_qs(location.query)
    assert location.netloc == "github.com"
    assert query["client_id"] == ["gh-client"]
    assert query["redirect_uri"] == ["https://api.hire.test/v1/auth/github/callback"]
    assert query["scope"] == ["read:user user:email"]  # never "repo": private code stays private
    cookie = resp.headers["set-cookie"].lower()
    assert "hire_oauth_state=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_github_login_creates_an_account_and_stores_the_token_encrypted(client, providers):
    resp = _login(client)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://app.hire.test/"

    me = client.get("/v1/me").json()
    assert me["email"] == "ana@example.com"
    assert me["display_name"] == "Ana Dev"
    assert me["providers"] == ["github"]

    with app_db(client) as db:
        identity = db.query(AuthIdentity).filter_by(provider="github").one()
        assert identity.subject == "4242" and identity.username == "ana-dev"
        assert identity.access_token_encrypted and "gho_secret_token" not in identity.access_token_encrypted
        assert decrypt_token(identity.access_token_encrypted) == "gho_secret_token"
        assert get_github_token(db, me["id"]) == "gho_secret_token"

    token_call = next(r for r in providers.requests if str(r.url) == oauth.GITHUB_TOKEN_URL)
    assert parse_qs(token_call.content.decode())["client_secret"] == ["gh-secret"]


def test_github_login_twice_is_the_same_account(client):
    first = _login(client)
    first_id = client.get("/v1/me").json()["id"]
    client.cookies.clear()
    _login(client)
    assert first.status_code == 302
    assert client.get("/v1/me").json()["id"] == first_id


def test_github_login_claims_unowned_pow_profiles_with_that_username(client):
    with app_db(client) as db:
        db.add(pow_models.User(username="Ana-Dev", analysis_mode="limited"))
        db.add(pow_models.User(username="someone-else", analysis_mode="limited"))
        db.commit()

    _login(client)
    me = client.get("/v1/me").json()
    with app_db(client) as db:
        owners = {u.username: u.account_id for u in db.query(pow_models.User).all()}
    assert owners == {"Ana-Dev": me["id"], "someone-else": None}


def test_state_mismatch_is_refused(client):
    client.get("/v1/auth/github/start", follow_redirects=False)
    resp = client.get("/v1/auth/github/callback?code=x&state=forged", follow_redirects=False)
    assert resp.status_code == 302
    assert "error=state_mismatch" in resp.headers["location"]
    assert client.get("/v1/me").status_code == 401


def test_callback_without_the_state_cookie_is_refused(client):
    resp = client.get("/v1/auth/github/callback?code=x&state=anything", follow_redirects=False)
    assert "error=state_mismatch" in resp.headers["location"]


def test_provider_refusing_the_code_is_a_clean_error(client, providers):
    providers.reject_code = True
    resp = _login(client)
    assert "error=provider_error" in resp.headers["location"]
    assert client.get("/v1/me").status_code == 401


def test_user_denying_consent_is_a_clean_error(client):
    start = client.get("/v1/auth/github/start", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    resp = client.get(f"/v1/auth/github/callback?error=access_denied&state={state}", follow_redirects=False)
    assert "error=denied" in resp.headers["location"]


def test_unconfigured_provider_is_503(client, monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", "")
    assert client.get("/v1/auth/google/start", follow_redirects=False).status_code == 503


def test_github_login_needs_an_encryption_key(client, monkeypatch):
    monkeypatch.setattr(settings, "token_encryption_key", "")
    resp = client.get("/v1/auth/github/start", follow_redirects=False)
    assert resp.status_code == 503
    assert "TOKEN_ENCRYPTION_KEY" in resp.json()["detail"]


def test_unknown_provider_is_404(client):
    assert client.get("/v1/auth/facebook/start", follow_redirects=False).status_code == 404


def test_google_login_works_and_keeps_no_token(client, providers):
    resp = _login(client, "google")
    assert resp.status_code == 302 and resp.headers["location"] == "https://app.hire.test/"
    me = client.get("/v1/me").json()
    assert me["providers"] == ["google"] and me["email"] == "ana@example.com"
    with app_db(client) as db:
        assert db.query(AuthIdentity).one().access_token_encrypted is None


def test_verified_provider_email_joins_the_existing_account(client):
    existing = create_account(client, "ana@example.com")
    _login(client, "google")
    me = client.get("/v1/me").json()
    assert me["id"] == existing.id
    assert me["providers"] == ["email", "google"]


def test_unverified_provider_email_never_claims_an_account(client, providers):
    existing = create_account(client, "ana@example.com")
    providers.google_info = {**GOOGLE_INFO, "email_verified": False}
    _login(client, "google")
    me = client.get("/v1/me").json()
    assert me["id"] != existing.id
    assert me["email"] is None


def test_github_without_a_verified_primary_email_still_logs_in(client, providers):
    providers.github_emails = [{"email": "ana@example.com", "primary": True, "verified": False}]
    _login(client)
    me = client.get("/v1/me").json()
    assert me["email"] is None and me["display_name"] == "Ana Dev"


def test_logged_in_user_links_github_to_their_account(client):
    # E.g. onboarding: logged in by email OTP, then "Connect GitHub".
    me_account = create_account(client, "different@example.com")
    login_as(client, me_account)
    _login(client)
    me = client.get("/v1/me").json()
    assert me["id"] == me_account.id
    assert me["providers"] == ["email", "github"]


def test_linking_an_identity_owned_by_someone_else_is_refused(client):
    _login(client)  # creates the GitHub account
    with app_db(client) as db:
        owner_id = db.query(AuthIdentity).filter_by(provider="github").one().account_id

    other = create_account(client, "other@example.com")
    login_as(client, other)
    resp = _login(client)
    assert "error=identity_in_use" in resp.headers["location"]
    with app_db(client) as db:
        assert db.query(AuthIdentity).filter_by(provider="github").one().account_id == owner_id


def test_erased_account_cannot_log_back_in(client):
    _login(client)
    with app_db(client) as db:
        account = db.query(Account).one()
        account.deleted_at = datetime.datetime(2026, 1, 1)
        db.commit()
    client.cookies.clear()
    resp = _login(client)
    assert "error=account_deleted" in resp.headers["location"]


def test_no_request_left_the_mock(client, providers):
    _login(client)
    _login(client, "google")
    hosts = {r.url.host for r in providers.requests}
    assert hosts <= {"github.com", "api.github.com", "oauth2.googleapis.com", "openidconnect.googleapis.com"}
