"""Regression tests for the bugs found in the 2026-10-15 review (PLAN.md §1.1)."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.applications import models as application_models
from app.applications.board import can_transition
from app.applications.consent import ConsentSecretMissing, ensure_signing_secret, issue_consent
from app.config import settings
from app.db import Base, get_db
from app.jobs import models as job_models  # noqa: F401
from app.jobs.ghost_filter.layoff_tracker import check_layoff_signal
from app.jobs.ingestion import feeds
from app.mail.classifier import classify_reply
from app.main import app
from app.services import fetch_service

CANDIDATE = "oshisharma1222"


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


def _swipe(client, job_id: str, direction: str) -> dict:
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")
    return client.post(
        "/api/applications/swipe",
        json={"job_id": job_id, "direction": direction, "candidate_ref": CANDIDATE},
    ).json()


# --- B1: layoff tracker -------------------------------------------------------

@pytest.mark.parametrize("domain", [None, "", "   "])
def test_b1_missing_domain_is_never_a_layoff_signal(domain):
    assert check_layoff_signal("Apex Edtech Corp", domain) == (False, None)


@pytest.mark.parametrize(
    "name, domain",
    [("Metamorph Labs", "metamorph.io"), ("BetterUp", "betterup.com"), ("Notbyjus", "notbyjus.com")],
)
def test_b1_lookalike_names_and_domains_are_not_flagged(name, domain):
    assert check_layoff_signal(name, domain)[0] is False


def test_b1_exact_domain_and_subdomains_are_flagged():
    assert check_layoff_signal("Byjus", "byjus.com")[0] is True
    assert check_layoff_signal("Byjus", "careers.byjus.com")[0] is True
    assert check_layoff_signal("Byjus", "WWW.BYJUS.COM")[0] is True


# --- B2: consent bypass -------------------------------------------------------

def test_b2_skipped_card_cannot_be_moved_onto_the_board_by_hand(session_and_client):
    _, client = session_and_client
    application_id = _swipe(client, "hyd_zepto_002", "left")["application"]["application_id"]

    for stage in ("applied", "interview_scheduled", "rejected"):
        moved = client.post(f"/api/applications/{application_id}/stage", json={"to_stage": stage})
        assert moved.status_code == 409, stage

    assert can_transition("skipped", "applied") is False
    board = client.get(f"/api/applications/board?candidate_ref={CANDIDATE}").json()
    assert board["total"] == 0


def test_b2_card_with_a_broken_receipt_cannot_move(session_and_client):
    Session, client = session_and_client
    application_id = _swipe(client, "blr_swig_001", "right")["application"]["application_id"]

    with Session() as db:
        log = db.query(application_models.ConsentLog).one()
        log.signature = "0" * 64
        db.commit()

    moved = client.post(f"/api/applications/{application_id}/stage", json={"to_stage": "interview_scheduled"})
    assert moved.status_code == 409


# --- B3: unsigned display columns --------------------------------------------

def test_b3_edited_display_column_fails_verification(session_and_client):
    Session, client = session_and_client
    swiped = _swipe(client, "blr_swig_001", "right")
    application_id = swiped["application"]["application_id"]
    assert swiped["consent"]["verified"] is True

    with Session() as db:
        log = db.query(application_models.ConsentLog).one()
        log.employer_name = "Some Other Employer"
        db.commit()

    receipt = client.get(f"/api/applications/{application_id}/consent").json()
    assert receipt["verified"] is False


# --- B4: default signing secret ----------------------------------------------

@pytest.mark.parametrize("secret", ["", "hire-unplug-dev-consent-secret", "too-short"])
def test_b4_missing_or_known_secret_refuses_to_sign(monkeypatch, secret):
    monkeypatch.setattr(settings, "consent_signing_secret", secret)
    with pytest.raises(ConsentSecretMissing):
        ensure_signing_secret()
    with pytest.raises(ConsentSecretMissing):
        issue_consent(subject="a", employer_name="b", job_id="c", role_title="d")


def test_b4_api_refuses_to_start_without_a_secret(monkeypatch):
    monkeypatch.setattr(settings, "consent_signing_secret", "")
    with pytest.raises(ConsentSecretMissing):
        with TestClient(app):
            pass


# --- B6: classifier minimum score --------------------------------------------

def test_b6_out_of_office_with_unfortunately_is_not_a_rejection():
    result = classify_reply(
        subject="Automatic reply: Out of office",
        body="Unfortunately I am away until Monday with limited access to email.",
    )
    assert result.stage is None


def test_b6_single_weak_hint_is_not_a_decision():
    assert classify_reply(subject="Re: update", body="I declined the meeting by mistake").stage is None


def test_b6_clear_rejection_still_counts():
    result = classify_reply(subject="Your application", body="We regret to inform you that we went another way.")
    assert result.stage == "rejected"


# --- B8: private repositories ------------------------------------------------

class _FakeGitHub:
    def __init__(self):
        self.analyzed: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_authenticated_login(self):
        return "ana"

    async def list_user_repos(self, username, authenticated=False, max_items=100):
        def repo(name, private):
            return {
                "full_name": f"ana/{name}", "name": name, "owner": {"login": "ana"},
                "html_url": f"https://github.com/ana/{name}", "private": private, "fork": False,
                "pushed_at": "2026-10-01T00:00:00Z",
            }
        return [repo("public-app", False), repo("secret-client-work", True)]

    async def list_user_commits(self, owner, repo, username, max_items):
        self.analyzed.append(f"{owner}/{repo}")
        return []

    async def list_contributors(self, owner, repo):
        return []

    async def search_external_merged_prs(self, username, limit):
        return []


def test_b8_private_repos_are_not_analysed_even_with_a_token():
    fake = _FakeGitHub()
    data = asyncio.run(fetch_service.fetch_contributions("ana", token="ghp_test", client=fake))
    assert fake.analyzed == ["ana/public-app"]
    assert [p["full_name"] for p in data["projects"]] == ["ana/public-app"]
    assert "secret-client-work" not in json.dumps(data, default=str)


# --- B10: hermetic tests ------------------------------------------------------

def test_b10_live_feeds_are_off_in_tests(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("tests must not touch the network")

    monkeypatch.setattr(feeds.httpx, "AsyncClient", boom)
    jobs = asyncio.run(feeds.fetch_public_feed_jobs(limit=50))
    assert [j["source_id"] for j in jobs] == [j["source_id"] for j in feeds.INDIAN_TECH_FIXTURES]
