"""Email OTP login: delivery, verification, expiry, tries and rate limits. No real mail is sent."""

import datetime

import pytest

from app.auth import mailer, otp
from app.auth.deps import CSRF_HEADER
from app.auth.models import Account, OtpCode
from app.config import settings
from auth_helpers import app_db, memory_client


class FakeSender:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, to: str, code: str) -> None:
        self.sent.append((to, code))

    @property
    def last_code(self) -> str:
        return self.sent[-1][1]


@pytest.fixture
def sender(monkeypatch):
    fake = FakeSender()
    monkeypatch.setattr(otp, "get_sender", lambda: fake)
    return fake


@pytest.fixture
def client(sender):
    with memory_client("https://testserver") as c:
        c.headers[CSRF_HEADER] = "hire-web"
        yield c


def _send(client, email="ana@example.com"):
    return client.post("/v1/auth/otp/send", json={"email": email})


def _verify(client, code, email="ana@example.com"):
    return client.post("/v1/auth/otp/verify", json={"email": email, "code": code})


def test_send_then_verify_logs_in(client, sender):
    resp = _send(client, "Ana@Example.com")
    assert resp.status_code == 202
    assert resp.json() == {"sent": True, "expires_in_seconds": 600}
    to, code = sender.sent[-1]
    assert to == "ana@example.com" and len(code) == 6 and code.isdigit()

    verified = _verify(client, code)
    assert verified.status_code == 200
    assert verified.json()["email"] == "ana@example.com"
    assert verified.json()["providers"] == ["email"]
    assert client.get("/v1/me").json()["id"] == verified.json()["id"]


def test_the_code_is_stored_hashed_and_works_once(client, sender):
    _send(client)
    with app_db(client) as db:
        row = db.query(OtpCode).one()
        assert sender.last_code not in row.code_hash
        assert row.code_hash == otp.hash_code("ana@example.com", sender.last_code)

    assert _verify(client, sender.last_code).status_code == 200
    assert _verify(client, sender.last_code).status_code == 400


def test_existing_account_with_that_email_is_reused(client, sender):
    _send(client)
    first = _verify(client, sender.last_code).json()
    _send(client)
    second = _verify(client, sender.last_code).json()
    assert first["id"] == second["id"]
    with app_db(client) as db:
        assert db.query(Account).count() == 1


def test_wrong_code_burns_a_try_and_five_lock_the_code(client, sender):
    _send(client)
    right = sender.last_code
    wrong = "000000" if right != "000000" else "111111"

    for _ in range(otp.MAX_ATTEMPTS):
        assert _verify(client, wrong).status_code == 400
    # Even the right code no longer works once the tries are used up.
    assert _verify(client, right).status_code == 429
    assert client.get("/v1/me").status_code == 401


def test_expired_code_is_rejected(client, sender):
    _send(client)
    with app_db(client) as db:
        db.query(OtpCode).one().expires_at = datetime.datetime(2000, 1, 1)
        db.commit()
    assert _verify(client, sender.last_code).status_code == 400


def test_a_new_code_supersedes_the_old_one(client, sender):
    _send(client)
    old = sender.last_code
    _send(client)
    new = sender.last_code
    if old != new:
        assert _verify(client, old).status_code == 400
    assert _verify(client, new).status_code == 200


def test_malformed_codes_and_emails_are_rejected(client, sender):
    assert _send(client, "not-an-email").status_code == 422
    _send(client)
    assert _verify(client, "12ab56").status_code == 400
    assert _verify(client, "").status_code == 400


def test_sends_are_rate_limited_per_email(client, sender):
    for _ in range(otp.MAX_SENDS_PER_EMAIL_PER_HOUR):
        assert _send(client).status_code == 202
    assert _send(client).status_code == 429
    # Another address is unaffected.
    assert _send(client, "bob@example.com").status_code == 202


def test_sends_are_rate_limited_per_ip(client, sender, monkeypatch):
    monkeypatch.setattr(otp, "MAX_SENDS_PER_IP_PER_HOUR", 3)
    for i in range(3):
        assert _send(client, f"user{i}@example.com").status_code == 202
    assert _send(client, "user9@example.com").status_code == 429


def test_send_does_not_reveal_whether_an_account_exists(client, sender):
    _send(client)
    _verify(client, sender.last_code)
    known = _send(client, "ana@example.com")
    unknown = _send(client, "nobody@example.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


def test_delivery_failure_is_a_502(monkeypatch):
    class Broken:
        def send(self, to, code):
            raise OSError("smtp down")

    monkeypatch.setattr(otp, "get_sender", lambda: Broken())
    with memory_client("https://testserver") as c:
        c.headers[CSRF_HEADER] = "hire-web"
        assert c.post("/v1/auth/otp/send", json={"email": "a@example.com"}).status_code == 502


# --- senders --------------------------------------------------------------------

def test_sender_choice_follows_env(monkeypatch):
    monkeypatch.setattr(settings, "otp_sender", "")
    monkeypatch.setattr(settings, "env", "dev")
    assert isinstance(mailer.get_sender(), mailer.ConsoleSender)
    monkeypatch.setattr(settings, "env", "prod")
    assert isinstance(mailer.get_sender(), mailer.SmtpSender)


def test_console_sender_is_refused_in_production(monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "otp_sender", "console")
    with pytest.raises(RuntimeError):
        mailer.get_sender()


def test_smtp_sender_sends_the_code(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "Hire <login@hire.example>")
    monkeypatch.setattr(settings, "smtp_user", "mailer")
    monkeypatch.setattr(settings, "smtp_password", "pw")

    mailer.SmtpSender().send("ana@example.com", "123456")

    assert sent["server"] == ("smtp.example.com", 587)
    assert sent["tls"] and sent["login"] == ("mailer", "pw")
    assert sent["msg"]["To"] == "ana@example.com"
    assert "123456" in sent["msg"]["Subject"] and "123456" in sent["msg"].get_content()


def test_smtp_sender_needs_a_host(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    with pytest.raises(RuntimeError):
        mailer.SmtpSender().send("a@example.com", "123456")
