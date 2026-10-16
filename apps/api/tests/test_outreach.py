"""Outreach drafts: grounded in the approved profile, returned for the user to send."""

import pytest

from app.facts.models import ProfileFact
from app.jobs.models import Company, Job
from app.llm.client import LLMError, get_llm_client
from app.llm.fake import FakeLLMClient
from app.main import app
from auth_helpers import app_db, create_account, login_as, memory_client

DRAFT = {"email_subject": "Backend engineer, payments", "email_body": "Hi,\nI built ...\nPriya",
         "linkedin_note": "Saw the backend role at Acme.", "highlights_used": ["Order batching at Zepto"]}


@pytest.fixture
def client():
    llm = FakeLLMClient(DRAFT)
    app.dependency_overrides[get_llm_client] = lambda: llm
    with memory_client() as c:
        c.llm = llm
        c.alice = create_account(c, "alice@example.com")
        login_as(c, c.alice)
        with app_db(c) as db:
            db.add(Company(id=1, name="Acme"))
            db.add(Job(job_id="j1", company_id=1, title="Backend Engineer", location="Bengaluru", ghost_score=100,
                       risk_band="Low", legitimacy_probability=0.9, primary_skills_json="[]", raw_description_hash="h",
                       raw_description="Build payment APIs in Go.", apply_url="https://boards.greenhouse.io/acme/jobs/1"))
            db.commit()
        yield c
    app.dependency_overrides.pop(get_llm_client, None)


def _approved(client, kind, text, **structured):
    with app_db(client) as db:
        db.add(ProfileFact(account_id=client.alice.id, kind=kind, text=text, structured=structured,
                           source="resume", status="approved"))
        db.commit()


def test_needs_something_real_in_the_profile_first(client):
    resp = client.post("/api/jobs/j1/outreach")
    assert resp.status_code == 422 and "profile" in resp.json()["detail"]
    assert client.llm.calls == []


def test_draft_uses_only_approved_facts_and_links_where_to_find_people(client):
    _approved(client, "experience", "Backend Engineer Intern at Zepto", company="Zepto", title="Backend Engineer Intern")
    _approved(client, "achievement", "Built order batching in Go, 35% faster", company="Zepto", title="Backend Engineer Intern")
    _approved(client, "link", "GitHub: github.com/priya", url="https://github.com/priya", network="github")
    with app_db(client) as db:
        db.add(ProfileFact(account_id=client.alice.id, kind="skill", text="Rust", structured={"name": "Rust"},
                           source="resume", status="proposed"))  # not approved: must not be used
        db.commit()

    body = client.post("/api/jobs/j1/outreach", json={"note": "I can join in 30 days"}).json()
    assert body["email_subject"] == DRAFT["email_subject"]
    assert "linkedin.com/search/results/people" in body["find_recruiter_url"] and "Acme" in body["find_recruiter_url"]
    assert body["company_careers_url"] == "https://boards.greenhouse.io/acme/jobs/1"

    sent = client.llm.calls[0]["content"][0]["text"]
    assert "order batching" in sent and "https://github.com/priya" in sent and "30 days" in sent
    assert "Rust" not in sent
    assert "<job_posting>" in sent and "payment APIs" in sent


def test_unknown_job_and_llm_failure(client):
    _approved(client, "experience", "Backend Engineer Intern at Zepto, Bengaluru, 2024", company="Zepto")
    assert client.post("/api/jobs/nope/outreach").status_code == 404
    client.llm.response = LLMError("down")
    assert client.post("/api/jobs/j1/outreach").status_code == 502
