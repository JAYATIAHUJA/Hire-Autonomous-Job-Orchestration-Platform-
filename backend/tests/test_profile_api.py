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
    {"name": "api", "full_name": "octo/api", "html_url": "https://github.com/octo/api", "fork": False,
     "pushed_at": "2025-01-01T00:00:00Z", "owner": {"login": "octo"}},
    {"name": "forked", "full_name": "octo/forked", "html_url": "https://github.com/octo/forked", "fork": True,
     "pushed_at": "2025-01-02T00:00:00Z", "owner": {"login": "octo"}},
]
COMMITS = [{"sha": f"sha{i}", "commit": {"author": {"date": f"2024-0{i + 1}-15T00:00:00Z"}}} for i in range(3)]


def fake_github(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/users/octo/repos":
        return httpx.Response(200, json=REPOS)
    if path == "/repos/octo/api/languages":
        return httpx.Response(200, json={"Python": 900})
    if path == "/repos/octo/api/commits":
        return httpx.Response(200, json=COMMITS)
    if path.startswith("/repos/octo/api/commits/"):
        sha = path.rsplit("/", 1)[1]
        return httpx.Response(200, json={"html_url": f"https://github.com/octo/api/commit/{sha}",
                                         "stats": {"additions": 10, "deletions": 2},
                                         "commit": {"message": "Add health endpoint\n\nbody"}})
    if path == "/search/issues":
        return httpx.Response(200, json={"items": [{"number": 1}]})
    if path == "/repos/octo/api/contents/requirements.txt":
        import base64
        return httpx.Response(200, json={"encoding": "base64", "content": base64.b64encode(b"fastapi\n").decode()})
    return httpx.Response(404, json={})


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    real_fetch = fetch_service.fetch_user_data
    monkeypatch.setattr(
        profile_router, "fetch_user_data",
        lambda username, token: real_fetch(username, token, client=GitHubClient(transport=httpx.MockTransport(fake_github))),
    )
    app.dependency_overrides[get_db] = override_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_analyze_then_fetch_profile(client):
    resp = client.post("/api/profile/analyze", json={"username": "octo"})
    assert resp.status_code == 200, resp.text
    profile_id = resp.json()["profile_id"]

    profile = client.get(f"/api/profile/{profile_id}").json()
    assert profile["username"] == "octo"
    assert profile["total_repos"] == 1  # fork excluded
    assert profile["total_commits"] == 3
    assert [p["month"] for p in profile["timeline"]] == ["2024-01", "2024-02", "2024-03"]

    skills = {s["name"]: s for s in profile["skills"]}
    assert {"Python", "FastAPI"} <= skills.keys()
    evidence = skills["FastAPI"]["evidence"][0]
    assert evidence["repo_url"] == "https://github.com/octo/api"
    assert evidence["sample_commit_message"] == "Add health endpoint"
    assert evidence["pr_count"] == 1


def test_unknown_profile_is_404(client):
    assert client.get("/api/profile/999").status_code == 404
