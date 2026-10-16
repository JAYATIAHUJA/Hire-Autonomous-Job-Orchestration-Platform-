"""WP1 x WP2 seam: PoW runs use the account's own stored GitHub token and linked login."""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.crypto import encrypt_token
from app.auth.models import Account, AuthIdentity
from app.auth.tokens import register_github_providers
from app.config import settings
from app.db import Base
from app.services import github_tokens


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    register_github_providers()
    yield session
    session.close()
    github_tokens.set_user_token_provider(None)
    github_tokens.set_linked_login_provider(None)


def test_linked_account_uses_its_own_token_and_login(db):
    linked, other = Account(email="priya@example.in"), Account(email="bob@example.com")
    db.add_all([linked, other])
    db.flush()
    db.add(AuthIdentity(account_id=linked.id, provider="github", subject="101", username="priyadev",
                        access_token_encrypted=encrypt_token("gho_user_token")))
    db.commit()

    assert github_tokens.linked_login(db, linked.id) == "priyadev"
    token, source = github_tokens.resolve_token(db, linked.id)
    assert token == "gho_user_token" and source == "user"

    assert github_tokens.linked_login(db, other.id) is None
    assert github_tokens.resolve_token(db, other.id)[1] != "user"
