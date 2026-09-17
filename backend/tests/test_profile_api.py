import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db import Base, get_db
from app.github_client import GitHubClient
from app.main import app
from app.routers import profile as profile_router
from app.services import fetch_service

REPOS = [
    {"name": "shop", "full_name": "ana/shop", "html_url": "https://github.com/ana/shop", "fork": False,
     "pushed_at": "2026-08-01T00:00:00Z", "owner": {"login": "ana"}},
    {"name": "forked", "full_name": "ana/forked", "html_url": "https://github.com/ana/forked", "fork": True,
     "pushed_at": "2026-08-02T00:00:00Z", "owner": {"login": "ana"}},
]
COMMIT_LIST = [
    {"sha": "c1", "parents": [{}], "commit": {"author": {"date": "2026-06-10T00:00:00Z"}}},
    {"sha": "c2", "parents": [{}], "commit": {"author": {"date": "2026-07-10T00:00:00Z"}}},
    {"sha": "m1", "parents": [{}, {}], "commit": {"author": {"date": "2026-07-11T00:00:00Z"}}},
]
COMMIT_DETAILS = {
    "c1": {
        "message": "feat: checkout page",
        "files": [
            {"filename": "src/Checkout.tsx", "additions": 220, "deletions": 5,
             "patch": "+import { useState } from 'react'\n+export function Checkout() {}"},
            {"filename": "package.json", "additions": 1, "deletions": 0, "patch": '+    "react": "^18.3.1",'},
            {"filename": "package-lock.json", "additions": 900, "deletions": 0, "patch": None},
        ],
    },
    "c2": {
        "message": "Add checkout tests",
        "files": [{"filename": "src/Checkout.test.tsx", "additions": 60, "deletions": 0,
                   "patch": "+import { render } from '@testing-library/react'"}],
    },
}
EXTERNAL_PR = {
    "number": 42, "title": "Add retry support to client", "html_url": "https://github.com/psf/requests/pull/42",
    "repository_url": "https://api.github.com/repos/psf/requests", "closed_at": "2026-05-01T00:00:00Z",
    "pull_request": {"merged_at": "2026-05-01T00:00:00Z"},
}


def fake_github(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    routes = {
        "/users/ana/repos": REPOS,
        "/repos/ana/shop/commits": COMMIT_LIST,
        "/repos/ana/shop/contributors": [{"login": "ana", "contributions": 9}, {"login": "bob", "contributions": 1}],
        "/search/issues": {"items": [EXTERNAL_PR]},
        "/repos/psf/requests/pulls/42/files": [
            {"filename": "src/requests/adapters.py", "additions": 140, "deletions": 20,
             "patch": "+import urllib3\n+from urllib3.util.retry import Retry"},
        ],
    }
    if path in routes:
        return httpx.Response(200, json=routes[path])
    if path.startswith("/repos/ana/shop/commits/"):
        sha = path.rsplit("/", 1)[1]
        d = COMMIT_DETAILS[sha]
        return httpx.Response(200, json={
            "html_url": f"https://github.com/ana/shop/commit/{sha}",
            "commit": {"message": d["message"], "author": {"date": next(c for c in COMMIT_LIST if c["sha"] == sha)["commit"]["author"]["date"]}},
            "files": d["files"],
        })
    return httpx.Response(404, json={"message": "Not Found"})


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    requested = []

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def recording(request):
        requested.append(request.url.path)
        return fake_github(request)

    real_fetch = fetch_service.fetch_contributions

    async def fake_fetch(username, token):
        return await real_fetch(username, token, client=GitHubClient(transport=httpx.MockTransport(recording)))

    monkeypatch.setattr(profile_router, "fetch_contributions", fake_fetch)
    app.dependency_overrides[get_db] = override_db
    test_client = TestClient(app)
    test_client.requested = requested
    yield test_client
    app.dependency_overrides.clear()


def test_analyze_builds_contribution_aware_profile(client):
    resp = client.post("/api/profile/analyze", json={"username": "ana"})
    assert resp.status_code == 200, resp.text
    profile = client.get(f"/api/profile/{resp.json()['profile_id']}").json()

    assert "/repos/ana/shop/commits/m1" not in client.requested  # merge commits are not analyzed
    assert profile["analysis_mode"] == "limited"
    assert profile["total_commits"] == 3
    assert profile["analyzed_contributions"] == 3
    assert profile["external_merged_prs"] == 1
    assert profile["meaningful_lines"] == 225 + 60 + 160  # lockfile excluded

    projects = {p["full_name"]: p for p in profile["projects"]}
    assert set(projects) == {"ana/shop", "psf/requests"}
    assert projects["ana/shop"]["role"] == "Primary author"
    assert projects["ana/shop"]["ownership_share"] == 0.9
    assert projects["psf/requests"]["role"] == "External contributor"

    assert {w["type"] for w in profile["work_mix"]} == {"feature", "test"}

    skills = {s["name"]: s for s in profile["skills"]}
    assert {"TypeScript", "React", "Automated Testing", "Python"} <= skills.keys()
    react = skills["React"]
    assert react["contribution_count"] == 1  # importing @testing-library/react is testing evidence, not React
    assert "Imports react in 1 changed file" in react["detected_via"]
    assert "Added dependency react" in react["detected_via"]
    assert skills["Automated Testing"]["contribution_count"] == 1
    assert react["highlights"][0]["url"] == "https://github.com/ana/shop/commit/c1"
    assert {f["label"] for f in react["factors"]} >= {"Substantial own code", "Accepted by others"}

    python = skills["Python"]
    assert python["external_pr_count"] == 1
    assert next(f for f in python["factors"] if f["label"] == "Accepted by others")["met"]

    assert profile["top_contributions"][0]["is_external"]  # merged PR to someone else's repo ranks first


def test_unknown_profile_is_404(client):
    assert client.get("/api/profile/999").status_code == 404
