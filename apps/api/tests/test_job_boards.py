"""Real jobs from employer boards: parsing, ingesting, closing, and discovery runs."""

import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base
from app.jobs import discovery, models, pipeline
from app.jobs.ingestion import ats_boards
from app.jobs.ingestion.ats_boards import BoardResult, experience_from_title, parse_board, plain_text

LONG = ("You will build payment APIs in Python, FastAPI, PostgreSQL, Redis and Kafka on AWS, own services "
        "end to end, write tests, review code and mentor juniors. 3+ years of backend experience.")

GREENHOUSE = {"jobs": [
    {"id": 1, "title": "Backend Engineer", "location": {"name": "Bengaluru, India"},
     "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "updated_at": "2026-10-10T10:00:00Z",
     "content": "&lt;p&gt;" + LONG + "&lt;/p&gt;"},
    {"id": 2, "title": "Account Executive", "location": {"name": "Mumbai, India"}, "absolute_url": "x"},
    {"id": 3, "title": "Software Engineer", "location": {"name": "Berlin, Germany"}, "absolute_url": "y"},
    {"id": 4, "title": "Data Engineer", "location": {"name": "Remote"}, "absolute_url": "https://g/4"},
]}
LEVER = [
    {"id": "abc", "text": "SDE Intern", "categories": {"location": "Pune"}, "hostedUrl": "https://jobs.lever.co/z/abc",
     "createdAt": 1760000000000, "descriptionPlain": LONG, "lists": [{"text": "You will", "content": "<li>ship</li>"}],
     "salaryRange": {"min": 50000, "max": 80000, "currency": "INR", "interval": "per-month"}},
]
ASHBY = {"jobs": [
    {"id": "q1", "title": "Senior ML Engineer", "location": "Hyderabad", "isRemote": False, "isListed": True,
     "jobUrl": "https://jobs.ashbyhq.com/n/q1", "publishedAt": "2026-10-01T00:00:00Z", "descriptionPlain": LONG,
     "compensation": {"compensationTierSummary": "₹40L – ₹60L"}},
    {"id": "q2", "title": "Platform Engineer", "location": "Delhi", "isListed": False},
]}


def test_greenhouse_keeps_tech_roles_in_india_or_remote():
    r = parse_board("greenhouse", "acme", "Acme", "acme.com", GREENHOUSE)
    assert [i["title"] for i in r.items] == ["Backend Engineer", "Data Engineer"]
    first = r.items[0]
    assert first["source"] == "greenhouse" and first["apply_url"] == "https://boards.greenhouse.io/acme/jobs/1"
    assert first["source_id"] == "greenhouse_acme_1" and "<p>" not in first["raw_description"]
    assert r.items[1]["is_remote"] is True
    assert r.seen_ids == {"greenhouse_acme_1", "greenhouse_acme_2", "greenhouse_acme_3", "greenhouse_acme_4"}


def test_lever_and_ashby_carry_salary_dates_and_links():
    lever = parse_board("lever", "z", "Zed", None, LEVER).items[0]
    assert lever["experience_level"] == "Internship" and lever["salary_range"].startswith("INR 50,000 - 80,000")
    assert lever["posted_at"] is not None and "ship" in lever["raw_description"]
    ashby = parse_board("ashby", "n", "Nova", None, ASHBY)
    assert [i["title"] for i in ashby.items] == ["Senior ML Engineer"]  # the unlisted one is skipped
    assert ashby.items[0]["salary_range"] == "₹40L – ₹60L"
    assert ashby.items[0]["experience_level"] == "Senior (5+ yrs)"


@pytest.mark.parametrize("title,level", [
    ("Software Engineer Intern", "Internship"), ("SDE II", "Mid-Level (2-5 yrs)"),
    ("Associate Software Engineer", "Entry-Level (0-2 yrs)"), ("Staff Engineer", "Senior (5+ yrs)"),
    ("Backend Engineer", "Not stated"), ("AI Engineer", "Not stated"),
])
def test_experience_from_title(title, level):
    assert experience_from_title(title) == level


def test_plain_text_unescapes_greenhouse_html():
    assert plain_text("&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Go&lt;/li&gt;") == "Hello & welcome\nGo"


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([
        {"name": "Acme", "ats": "greenhouse", "board_token": "acme", "probed_at": "2026-10-01T00:00:00Z"},
    ]), encoding="utf-8")
    monkeypatch.setattr(settings, "ats_registry_path", str(registry))
    monkeypatch.setattr(settings, "ats_boards_per_round", 10)
    monkeypatch.setattr(settings, "demo_jobs_enabled", False)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _serve(monkeypatch, payload):
    async def fake(boards):
        return [parse_board(ats, token, name, domain, payload) for ats, token, name, domain in boards]

    monkeypatch.setattr(pipeline, "fetch_boards", fake)


def test_a_round_loads_the_registry_ingests_and_later_closes_jobs(db, monkeypatch):
    _serve(monkeypatch, GREENHOUSE)
    stats = asyncio.run(pipeline.run_discovery_cycle(db))
    assert stats["boards_checked"] == 1 and stats["jobs_added"] == 2
    job = db.query(models.Job).filter_by(job_id="greenhouse_acme_1").one()
    assert (job.source, job.apply_url, job.is_active) == ("greenhouse", "https://boards.greenhouse.io/acme/jobs/1", True)
    assert job.posted_at is not None and job.last_seen_at is not None

    # The board drops job 4: it closes. Job 1 is still listed: it stays, counted as updated.
    _serve(monkeypatch, {"jobs": [GREENHOUSE["jobs"][0]]})
    stats = asyncio.run(pipeline.run_discovery_cycle(db))
    assert stats["jobs_closed"] == 1 and stats["jobs_added"] == 0 and stats["jobs_updated"] == 1
    assert db.query(models.Job).filter_by(job_id="greenhouse_acme_4").one().is_active is False


def test_a_failed_board_closes_nothing(db, monkeypatch):
    _serve(monkeypatch, GREENHOUSE)
    asyncio.run(pipeline.run_discovery_cycle(db))

    async def down(boards):
        return [BoardResult(ok=False, error="HTTP 503") for _ in boards]

    monkeypatch.setattr(pipeline, "fetch_boards", down)
    stats = asyncio.run(pipeline.run_discovery_cycle(db))
    assert stats["boards_failed"] == 1 and stats["jobs_closed"] == 0
    assert db.query(models.Job).filter_by(is_active=True).count() == 2


def test_sample_jobs_are_switched_off_in_real_use(db, monkeypatch):
    _serve(monkeypatch, {"jobs": []})
    db.add(models.Company(id=99, name="Fake Co"))
    db.add(models.Job(job_id="sample_1", company_id=99, title="t", location="l", ghost_score=10, risk_band="Low",
                      legitimacy_probability=0.9, primary_skills_json="[]", raw_description_hash="h",
                      source="sample", is_active=True))
    db.commit()
    asyncio.run(pipeline.run_discovery_cycle(db))
    assert db.query(models.Job).filter_by(job_id="sample_1").one().is_active is False


def test_requested_runs_are_claimed_once_and_scheduled_runs_wait(db, monkeypatch):
    monkeypatch.setattr(settings, "discovery_interval_seconds", 3600)
    first = discovery.claim_run(db)  # nothing ever ran: a scheduled run is due
    assert first is not None and first.status == "running"
    assert discovery.claim_run(db) is None  # one at a time
    discovery.finish_run(db, first, {"jobs_added": 5, "boards_checked": 2})
    assert discovery.claim_run(db) is None  # ran a moment ago

    requested = discovery.request_run(db)
    assert discovery.request_run(db).id == requested.id  # no pile-up of requests
    status = discovery.status(db)
    assert status.current_run.status == "requested" and status.last_run.jobs_added == 5
    claimed = discovery.claim_run(db)
    assert claimed.id == requested.id and claimed.status == "running"


def test_discovery_endpoints(monkeypatch):
    from auth_helpers import create_account, login_as, memory_client

    with memory_client() as client:
        login_as(client, create_account(client, "a@example.com"))
        assert client.get("/api/jobs/discovery").json()["current_run"] is None
        body = client.post("/api/jobs/discovery").json()
        assert body["current_run"]["status"] == "requested"
        assert client.post("/api/jobs/discovery").json()["current_run"]["id"] == body["current_run"]["id"]


def test_the_feed_shows_where_a_job_came_from(db, monkeypatch):
    from app.jobs.repository import get_job_by_id, get_jobs_feed

    _serve(monkeypatch, GREENHOUSE)
    asyncio.run(pipeline.run_discovery_cycle(db))
    jobs, _ = get_jobs_feed(db, min_legitimacy=0.0, limit=10)
    backend = next(j for j in jobs if j.job_id == "greenhouse_acme_1")
    assert backend.source.name == "greenhouse" and backend.source.apply_url.endswith("/jobs/1")
    assert len(backend.description) <= 400
    assert get_job_by_id(db, "greenhouse_acme_1").description.startswith("You will build")
    _ = ats_boards  # imported for monkeypatch targets in other tests


def test_ghost_jobs_are_not_counted_as_added_or_updated(db, monkeypatch):
    ghost = {"id": 9, "title": "Rockstar Ninja Developer", "location": {"name": "Remote"}, "absolute_url": "g",
             "updated_at": "2025-01-01T00:00:00Z", "content": "hustle"}
    _serve(monkeypatch, {"jobs": [GREENHOUSE["jobs"][0], ghost]})
    stats = asyncio.run(pipeline.run_discovery_cycle(db))
    assert stats["jobs_added"] == 1 and stats["ghosts_filtered"] == 1 and stats["jobs_updated"] == 0


def test_feed_search_city_remote_and_newest(db, monkeypatch):
    from app.jobs.repository import get_jobs_feed

    _serve(monkeypatch, GREENHOUSE)
    asyncio.run(pipeline.run_discovery_cycle(db))
    titles = lambda **kw: [j.role.title for j in get_jobs_feed(db, min_legitimacy=0.0, **kw)[0]]  # noqa: E731
    assert titles(q="backend") == ["Backend Engineer"]
    assert set(titles(q="acme")) == {"Backend Engineer", "Data Engineer"}
    assert titles(city="bengaluru") == ["Backend Engineer"]
    assert titles(remote=True) == ["Data Engineer"]
    assert titles(newest_first=True)[0] == "Backend Engineer"  # the only one with a posted date sorts first


def test_feed_html_and_broken_quotes_become_readable_text():
    from app.jobs.ingestion.ats_boards import fix_mojibake

    raw = '<p style="min-height:1.5em"><strong>About Us:</strong></p><p>Weâ€™re building it.</p>'
    assert plain_text(raw) == "About Us:\nWe’re building it."
    assert fix_mojibake("Weâ€™re") == "We’re" and fix_mojibake("plain") == "plain"


@pytest.mark.parametrize("location,ok", [
    ("", True), ("Worldwide", True), ("Remote", True), ("India", True), ("APAC", True),
    ("USA", False), ("Remote - USA / Canada", False), ("United States", False), ("Europe", False),
])
def test_remoteok_keeps_roles_open_to_india(location, ok):
    from app.jobs.ingestion.ats_boards import open_to_india

    assert open_to_india(location) is ok


def test_public_stats_need_no_login_and_reveal_only_counts():
    from fastapi.testclient import TestClient

    from auth_helpers import memory_client

    with memory_client() as client:
        anon = TestClient(client.app)
        body = anon.get("/v1/public/stats").json()
        assert set(body) == {"live_jobs", "companies_hiring", "boards_tracked", "ghosts_filtered"}
        assert all(isinstance(v, int) for v in body.values())


def test_remote_roles_must_be_open_to_india():
    zurich = {"jobs": [
        {"id": "z1", "title": "Full Stack Engineer, AI systems", "location": "Zurich, Switzerland", "isRemote": True,
         "isListed": True, "jobUrl": "u", "descriptionPlain": LONG,
         "address": {"postalAddress": {"addressCountry": "Switzerland"}}},
        {"id": "z2", "title": "Backend Engineer", "location": "Remote", "isRemote": True, "isListed": True,
         "jobUrl": "u2", "descriptionPlain": LONG},
        {"id": "z3", "title": "Backend Engineer", "location": "Remote - India", "isRemote": True, "isListed": True,
         "jobUrl": "u3", "descriptionPlain": LONG},
    ]}
    titles = [(i["source_id"]) for i in parse_board("ashby", "b", "Bjak", None, zurich).items]
    assert titles == ["ashby_b_z2", "ashby_b_z3"]
    gh = {"jobs": [{"id": 7, "title": "SRE", "location": {"name": "Remote - USA"}, "absolute_url": "x"}]}
    assert parse_board("greenhouse", "g", "G", None, gh).items == []


def test_stored_jobs_that_fail_the_rule_are_closed(db, monkeypatch):
    _serve(monkeypatch, {"jobs": []})
    db.add(models.Company(id=50, name="Bjak"))
    for jid, loc in (("a", "Zurich, Switzerland"), ("b", "Bengaluru, India"), ("c", "Remote")):
        db.add(models.Job(job_id=jid, company_id=50, title="Engineer", location=loc, ghost_score=10, risk_band="Low",
                          legitimacy_probability=0.9, primary_skills_json="[]", raw_description_hash="h",
                          source="ashby", is_active=True, is_remote=True))
    db.commit()
    asyncio.run(pipeline.run_discovery_cycle(db))
    assert {j.job_id: j.is_active for j in db.query(models.Job).filter_by(company_id=50)} == {"a": False, "b": True, "c": True}


def test_feed_filters_level_salary_recency_and_best_match():
    from datetime import datetime, timedelta, timezone

    from auth_helpers import app_db, create_account, login_as, memory_client

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with memory_client() as client:
        login_as(client, create_account(client, "f@example.com"))
        client.patch("/v1/me/preferences", json={"roles": ["Backend engineer"], "locations": ["Pune"], "remote_ok": False,
                                                 "experience_band": "0-1"})
        with app_db(client) as db:
            db.add(models.Company(id=1, name="Acme"))
            rows = [("a", "Backend Engineer Intern", "Pune", "Internship", "₹40k/month", 2),
                    ("b", "Frontend Engineer", "Delhi", "Entry-Level (0-2 yrs)", None, 40),
                    ("c", "Staff Backend Engineer", "Pune", "Senior (5+ yrs)", None, 1)]
            for jid, title, loc, level, salary, age in rows:
                db.add(models.Job(job_id=jid, company_id=1, title=title, location=loc, experience_level=level,
                                  salary_range=salary, ghost_score=10, risk_band="Low", legitimacy_probability=0.9,
                                  primary_skills_json="[]", raw_description_hash=jid, source="greenhouse",
                                  posted_at=now - timedelta(days=age), is_active=True))
            db.commit()
        ids = lambda **p: [j["job_id"] for j in client.get("/api/jobs/feed", params=p).json()["jobs"]]  # noqa: E731
        assert ids(level="intern") == ["a"]
        assert sorted(ids(level="entry,senior")) == ["b", "c"]
        assert ids(salary_shown="true") == ["a"]
        assert sorted(ids(posted_within=7)) == ["a", "c"]
        best = client.get("/api/jobs/feed", params={"sort": "match"}).json()["jobs"]
        assert best[0]["job_id"] == "a" and best[0]["match"]["percent"] > 0
