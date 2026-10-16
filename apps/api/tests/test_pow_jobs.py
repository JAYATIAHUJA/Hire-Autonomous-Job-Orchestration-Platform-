"""refresh -> worker -> poll -> done, and the Evidence Index, against recorded GitHub fixtures."""

import asyncio
import datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.auth.deps import Account, get_current_user
from app.db import Base, get_db
from app.github_client import ETagCache, GitHubClient
from app.main import app
from app.profiles.pow_models import PowEvidence, PowRun
from app.services import github_tokens, pow_service
from pow_github_fixtures import FixtureGitHub, load

ANA, BOB = Account(id=1, email="priya@example.in"), Account(id=2, email="bob@example.com")


class Env:
    def __init__(self, client: TestClient, Session: sessionmaker):
        self.client, self.Session = client, Session
        self.account = ANA
        self.github = FixtureGitHub()

    def as_(self, account: Account) -> "Env":
        self.account = account
        return self

    def work(self) -> int | None:
        """Run one worker step, as python -m app.worker would."""
        factory = lambda token: GitHubClient(token=token, transport=self.github.transport(), etag_cache=ETagCache(256))
        return asyncio.run(pow_service.process_next(self.Session, factory))

    def refresh(self, **body):
        return self.client.post("/v1/profile/pow/refresh", json={"github_username": "priyadev", **body})

    def run(self, run_id: int):
        return self.client.get(f"/v1/profile/pow/runs/{run_id}")

    def evidence(self, **params):
        return self.client.get("/v1/profile/evidence", params=params)


@pytest.fixture
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    e = Env(TestClient(app), Session)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: e.account
    # Account 1 has linked GitHub (WP1 seam); account 2 has not.
    github_tokens.set_user_token_provider(lambda db, account_id: "user-token" if account_id == ANA.id else None)
    yield e
    github_tokens.set_user_token_provider(None)
    github_tokens.set_linked_login_provider(None)
    app.dependency_overrides.clear()


def fixture_urls() -> set[str]:
    urls = {r["html_url"] for r in load("user__repos.json")}
    for repo in ("shopfront", "fieldnotes-mobile", "ledger-api", "salary-notes"):
        urls |= {c["html_url"] for c in load(f"repos__priyadev__{repo}__commits.json")}
    urls |= {i["html_url"] for i in load("search__issues.json")["items"]}
    urls.add("https://github.com/encode/httpx")
    return urls


# --- refresh -> poll -> done ---------------------------------------------------------------

def test_refresh_poll_done(env):
    resp = env.refresh()
    assert resp.status_code == 202, resp.text
    run = resp.json()
    assert (run["status"], run["progress"]) == ("queued", 0)
    assert env.run(run["id"]).json()["status"] == "queued"

    assert env.work() == run["id"]
    assert env.work() is None  # queue drained

    done = env.run(run["id"]).json()
    assert done["status"] == "done" and done["progress"] == 100 and done["error"] is None
    assert done["started_at"] and done["finished_at"]
    cov = done["sample_coverage"]
    assert (cov["sampled_commits"], cov["total_commits"]) == (18, 19)
    assert cov["commits_last_year"] == 412

    profile = env.client.get(f"/api/profile/{done['profile_id']}").json()
    assert {p["full_name"] for p in profile["projects"]} == {
        "priyadev/shopfront", "priyadev/fieldnotes-mobile", "priyadev/ledger-api", "encode/httpx"}
    assert "/graphql" in env.github.paths and "/user/repos" in env.github.paths  # user's own token was used


def test_one_active_run_per_account(env):
    first = env.refresh().json()
    again = env.refresh()
    assert again.status_code == 200 and again.json()["id"] == first["id"]

    other = env.as_(BOB).refresh()
    assert other.status_code == 202 and other.json()["id"] != first["id"]

    env.as_(ANA).work()
    env.work()
    assert env.refresh().status_code == 202  # finished runs don't block a new refresh


def test_partial_unique_index_blocks_a_second_active_run(env):
    db = env.Session()
    db.add_all([PowRun(account_id=9, github_username="x", status="done"),
                PowRun(account_id=9, github_username="x", status="done"),
                PowRun(account_id=9, github_username="x", status="queued")])
    db.commit()
    db.add(PowRun(account_id=9, github_username="x", status="running"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()


def test_runs_are_owner_scoped(env):
    run_id = env.refresh().json()["id"]
    assert env.as_(BOB).run(run_id).status_code == 404
    assert env.as_(BOB).run(99999).status_code == 404


def test_login_is_required():
    app.dependency_overrides.clear()
    client = TestClient(app)
    assert client.post("/v1/profile/pow/refresh", json={"github_username": "priyadev"}).status_code == 401
    assert client.get("/v1/profile/evidence").status_code == 401


def test_username_must_match_the_linked_github_account(env):
    github_tokens.set_linked_login_provider(lambda db, account_id: "priyadev")
    assert env.refresh(github_username="someone-else").status_code == 422
    resp = env.client.post("/v1/profile/pow/refresh", json={})  # falls back to the linked login
    assert resp.status_code == 202 and resp.json()["github_username"] == "priyadev"


def test_username_is_required_without_a_linked_account(env):
    assert env.client.post("/v1/profile/pow/refresh", json={}).status_code == 422
    assert env.refresh(github_username="bad name!").status_code == 422


def test_app_token_is_used_when_the_user_has_not_linked_github(env, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "github_app_token", "app-token")
    run_id = env.as_(BOB).refresh().json()["id"]
    env.work()
    assert env.run(run_id).json()["status"] == "done"
    auth = {r.headers.get("Authorization") for r in env.github.requests}
    assert auth == {"Bearer app-token"}
    assert "/users/priyadev/repos" in env.github.paths  # app token is not priyadev's: public repos only


def test_rate_limit_fails_the_run_with_a_clear_error(env):
    env.github.handle = lambda request: httpx.Response(403, headers={"X-RateLimit-Remaining": "0"}, json={})
    run_id = env.refresh().json()["id"]
    env.work()
    run = env.run(run_id).json()
    assert run["status"] == "failed" and "rate limit" in run["error"].lower()
    assert env.refresh().status_code == 202  # a failed run doesn't block retrying


def test_unknown_github_user_fails_the_run(env):
    env.github = FixtureGitHub(graphql="user_not_found")
    run_id = env.refresh(github_username="no-such-user-xyz").json()["id"]
    env.work()
    run = env.run(run_id).json()
    assert run["status"] == "failed" and "not found" in run["error"]


def test_stale_running_run_is_failed_not_replayed(env):
    run_id = env.refresh().json()["id"]
    db = env.Session()
    run = db.get(PowRun, run_id)
    run.status = "running"
    run.started_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=2)
    db.commit()
    db.close()

    fresh = env.refresh()
    assert fresh.status_code == 202 and fresh.json()["id"] != run_id
    stale = env.run(run_id).json()
    assert stale["status"] == "failed" and "Interrupted" in stale["error"]


def test_worker_drains_the_queue_before_sleeping(monkeypatch):
    from app import worker

    results, stop = iter([1, 2, None]), asyncio.Event()
    seen = []

    async def fake_round():
        r = next(results)
        seen.append(r)
        if r is None:
            stop.set()
        return r

    monkeypatch.setattr(worker, "pow_round", fake_round)
    asyncio.run(worker.pow_loop(stop))
    assert seen == [1, 2, None]


# --- Evidence Index ------------------------------------------------------------------------

def _done(env, **body):
    env.refresh(**body)
    env.work()


def test_evidence_rows_cite_real_public_urls(env):
    _done(env)
    rows = env.evidence(limit=200).json()["evidence"]
    assert rows
    known = fixture_urls()
    assert all(r["url"] in known for r in rows), [r["url"] for r in rows if r["url"] not in known]
    assert {r["kind"] for r in rows} <= {"commit", "pr", "repo"}
    assert not any(r["is_private"] or "salary-notes" in r["url"] for r in rows)


def test_evidence_by_skill_is_whole_token(env):
    _done(env)
    react = env.evidence(skill="react").json()["evidence"]
    assert react and {r["skill"] for r in react} == {"React"}
    assert {r["repo"] for r in react} == {"priyadev/shopfront"}  # not the React Native app
    assert any(r["kind"] == "repo" and r["url"] == "https://github.com/priyadev/shopfront" for r in react)

    rn = env.evidence(skill="React Native").json()["evidence"]
    assert {r["repo"] for r in rn} == {"priyadev/fieldnotes-mobile"}

    next_rows = env.evidence(skill="next.js").json()["evidence"]
    nextauth_rows = env.evidence(skill="nextauth.js").json()["evidence"]
    nextauth_commit = next(c["html_url"] for c in load("repos__priyadev__shopfront__commits.json")
                           if c["commit"]["message"].startswith("feat(auth)"))
    assert nextauth_commit in {r["url"] for r in nextauth_rows}
    assert nextauth_commit not in {r["url"] for r in next_rows}  # next-auth is not Next.js


def test_evidence_includes_merged_external_pr(env):
    _done(env)
    python = env.evidence(skill="python").json()["evidence"]
    pr = next(r for r in python if r["kind"] == "pr")
    assert pr["url"] == "https://github.com/encode/httpx/pull/3120"
    assert pr["summary"].startswith("Merged pull request")


def test_evidence_is_owner_scoped(env):
    _done(env)
    assert env.as_(BOB).evidence().json()["evidence"] == []


def test_private_evidence_is_hidden_unless_asked_for(env):
    _done(env, include_private=True)
    assert not any(r["is_private"] for r in env.evidence(limit=200).json()["evidence"])

    pandas = env.evidence(skill="pandas", include_private="true").json()["evidence"]
    assert pandas and all(r["is_private"] and r["repo"] == "priyadev/salary-notes" for r in pandas)

    run = env.client.get("/v1/profile/pow/runs/1").json()
    profile = env.client.get(f"/api/profile/{run['profile_id']}").json()
    assert "salary-notes" not in str(profile)  # the public profile never shows private work


def test_new_run_replaces_evidence_and_old_profile(env):
    _done(env)
    first_profile = env.client.get("/v1/profile/pow/runs/1").json()["profile_id"]
    _done(env)
    second = env.client.get("/v1/profile/pow/runs/2").json()
    db = env.Session()
    assert {e.run_id for e in db.query(PowEvidence).all()} == {2}
    db.close()
    assert env.client.get(f"/api/profile/{first_profile}").status_code == 404
    assert env.client.get(f"/api/profile/{second['profile_id']}").status_code == 200


def test_erase_removes_runs_evidence_and_profiles(env):
    _done(env)
    profile_id = env.client.get("/v1/profile/pow/runs/1").json()["profile_id"]
    env.as_(BOB).refresh()

    assert env.as_(ANA).client.delete("/v1/profile/pow").status_code == 204
    assert env.run(1).status_code == 404
    assert env.evidence().json()["evidence"] == []
    assert env.client.get(f"/api/profile/{profile_id}").status_code == 404
    db = env.Session()
    assert [r.account_id for r in db.query(PowRun).all()] == [BOB.id]  # other accounts untouched
    db.close()
