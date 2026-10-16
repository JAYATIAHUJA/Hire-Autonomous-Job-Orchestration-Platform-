"""Log a TestClient in without going through OTP or OAuth.

    from auth_helpers import create_account, login_as  # tests/ is on sys.path under pytest

    alice = create_account(client, "alice@example.com")
    login_as(client, alice)           # every later request is alice's
    client.get("/v1/me").json()["id"] == alice.id

Both helpers write through whatever ``get_db`` the app is using, including a test's
``app.dependency_overrides[get_db]``, so they work with any in-memory database.
"""

from contextlib import contextmanager
from typing import Iterator, Optional, Union

from fastapi.testclient import TestClient

from app.auth.deps import CSRF_HEADER
from app.auth.models import Account, AuthIdentity
from app.auth.sessions import create_session
from app.config import settings
from app.db import get_db

TEST_CSRF_VALUE = "hire-test"


@contextmanager
def app_db(client: TestClient) -> Iterator:
    """A database session from the app's (possibly overridden) ``get_db``."""
    factory = client.app.dependency_overrides.get(get_db, get_db)
    gen = factory()
    db = next(gen)
    try:
        yield db
    finally:
        gen.close()


def create_account(
    client: TestClient,
    email: Optional[str] = None,
    *,
    role: str = "user",
    display_name: Optional[str] = None,
) -> Account:
    """Insert an account (with an email identity when ``email`` is given) and return it detached."""
    with app_db(client) as db:
        account = Account(email=email.lower() if email else None, display_name=display_name or email, role=role)
        db.add(account)
        db.flush()
        if email:
            db.add(AuthIdentity(account_id=account.id, provider="email", subject=email.lower(), email=email.lower()))
        db.commit()
        db.refresh(account)
        db.expunge(account)
        return account


def login_as(client: TestClient, account: Union[Account, int]) -> str:
    """Start a real session for ``account`` and make the client send it (cookie + CSRF header).

    Calling it again switches the client to another account. Returns the raw token.
    """
    account_id = account if isinstance(account, int) else account.id
    with app_db(client) as db:
        token = create_session(db, db.get(Account, account_id))
    client.cookies.set(settings.session_cookie_name, token)
    client.headers[CSRF_HEADER] = TEST_CSRF_VALUE
    return token


def logout(client: TestClient) -> None:
    client.cookies.clear()
    client.headers.pop(CSRF_HEADER, None)


@contextmanager
def memory_client(base_url: str = "http://testserver") -> Iterator[TestClient]:
    """A TestClient on a fresh in-memory database. Pass an ``https://`` base_url to let
    the client store and resend the Secure session cookie set by real login endpoints."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import Base
    from app.main import app

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
    try:
        yield TestClient(app, base_url=base_url)
    finally:
        app.dependency_overrides.pop(get_db, None)


def login_new_account(client: TestClient, email: str, *, role: str = "user") -> Account:
    """Shortcut: create an account and log the client in as it."""
    account = create_account(client, email, role=role)
    login_as(client, account)
    return account
