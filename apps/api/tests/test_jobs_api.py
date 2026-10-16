import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.jobs import models as job_models  # noqa: F401
from app.main import app


@pytest.fixture
def client():
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
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_score_job_endpoint(client):
    payload = {
        "posting_age_days": 5,
        "repost_count": 0,
        "raw_description": "We are hiring a Backend Engineer to build microservices with Python, FastAPI, PostgreSQL, and Docker.",
        "salary_range": "₹12,00,000 - ₹18,00,000 INR",
        "company_name": "Acme Systems",
        "company_domain": "acme.io",
        "external_layoff_flag": False,
    }
    resp = client.post("/jobs/score", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ghost_score"] < 400
    assert data["risk_band"] == "Low"
    assert data["is_ghost"] is False
    assert data["legitimacy_probability"] >= 0.60
    assert "fastapi" in data["features"]["detected_skills"]


def test_feed_and_ghost_purging_rule(client):
    # GET /jobs/feed triggers initial discovery ingestion from fixtures
    resp = client.get("/jobs/feed?limit=20&min_legitimacy=0.6")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] > 0
    assert len(data["jobs"]) > 0

    # Ensure none of the returned jobs are ghost jobs (ghost_score >= 700)
    for job in data["jobs"]:
        assert job["ghost_job_metrics"]["ghost_score"] < 700
        assert job["ghost_job_metrics"]["legitimacy_probability"] >= 0.60
        assert job["ghost_job_metrics"]["risk_band"] in {"Low", "Moderate"}

        # Verify exact Shared Data Contract schema
        assert "job_id" in job
        assert "name" in job["company"]
        assert "domain" in job["company"]
        assert "external_layoff_flag" in job["company"]
        assert "title" in job["role"]
        assert "location" in job["role"]
        assert "primary_skills" in job["parsed_requirements"]
        assert "raw_description_hash" in job["parsed_requirements"]
        assert len(job["parsed_requirements"]["raw_description_hash"]) == 32

    # High-risk ghost jobs (e.g. apex-edtech-layoff and talentpool-harvest) must be purged from feed
    job_ids = {j["job_id"] for j in data["jobs"]}
    assert "ghost_corp_005" not in job_ids
    assert "ghost_harvest_006" not in job_ids


def test_get_job_by_id_and_not_found(client):
    # Seed feed first
    client.get("/jobs/feed")

    # Fetch valid job
    resp = client.get("/jobs/blr_swig_001")
    assert resp.status_code == 200
    job = resp.json()
    assert job["job_id"] == "blr_swig_001"
    assert job["company"]["name"] == "Swiggy Engineering"
    assert "FastAPI" in job["parsed_requirements"]["primary_skills"]

    # Fetch unknown job
    missing = client.get("/jobs/nonexistent_job_id")
    assert missing.status_code == 404


def test_cache_check_endpoint(client):
    # Description not cached yet
    desc = "Brand new unique JD text never seen before in system."
    check_resp = client.post("/jobs/cache-check", json={"raw_description": desc})
    assert check_resp.status_code == 200
    assert check_resp.json()["cached"] is False
    assert len(check_resp.json()["hash"]) == 32
