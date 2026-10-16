"""Profile versions: one master profile, cut for different kinds of role."""

import pytest

from app.facts.models import ProfileFact
from auth_helpers import app_db, create_account, login_as, memory_client


@pytest.fixture
def client():
    with memory_client() as c:
        c.alice = create_account(c, "alice@example.com")
        c.bob = create_account(c, "bob@example.com")
        login_as(c, c.alice)
        yield c


def _fact(client, kind, text, status="approved", account=None, **structured):
    with app_db(client) as db:
        f = ProfileFact(account_id=(account or client.alice).id, kind=kind, text=text, structured=structured,
                        source="resume", status=status)
        db.add(f)
        db.commit()
        return f.id


def test_a_version_shows_only_its_chosen_facts_plus_identity(client):
    name = _fact(client, "name", "Priya Sharma")
    backend = _fact(client, "project", "Payments API in Go", name="Payments API")
    ml = _fact(client, "project", "Churn model in PyTorch", name="Churn model")
    go = _fact(client, "skill", "Go", name="Go")
    _fact(client, "skill", "PyTorch", name="PyTorch")

    v = client.post("/v1/profile/versions", json={"name": "Backend", "headline": "Backend engineer, Go and Postgres",
                                                  "target_role": "Backend engineer", "fact_ids": [backend, go, name]}).json()
    assert v["fact_ids"] == [backend, go]  # identity facts always come along, so they are not "chosen"
    doc = client.get(f"/v1/profile/versions/{v['id']}/document").json()
    assert [p["text"] for p in doc["projects"]] == ["Payments API in Go"]
    assert [s["text"] for s in doc["skills"]] == ["Go"]
    assert doc["identity"]["name"]["value"] == "Priya Sharma"
    assert doc["version"]["headline"] == "Backend engineer, Go and Postgres"
    assert ml not in v["fact_ids"]


def test_versions_only_take_my_approved_facts(client):
    pending = _fact(client, "skill", "Rust", status="proposed")
    theirs = _fact(client, "skill", "Java", account=client.bob)
    v = client.post("/v1/profile/versions", json={"name": "X", "fact_ids": [pending, theirs]}).json()
    assert v["fact_ids"] == []


def test_list_update_delete_and_privacy(client):
    v = client.post("/v1/profile/versions", json={"name": "Data"}).json()
    assert [x["name"] for x in client.get("/v1/profile/versions").json()] == ["Data"]
    assert client.put(f"/v1/profile/versions/{v['id']}", json={"name": "Data & ML"}).json()["name"] == "Data & ML"
    login_as(client, client.bob)
    assert client.get("/v1/profile/versions").json() == []
    assert client.get(f"/v1/profile/versions/{v['id']}/document").status_code == 404
    assert client.delete(f"/v1/profile/versions/{v['id']}").status_code == 404
    login_as(client, client.alice)
    assert client.delete(f"/v1/profile/versions/{v['id']}").status_code == 204
    assert client.get("/v1/profile/versions").json() == []


def test_outreach_writes_from_the_chosen_version():
    from app.jobs.models import Company, Job
    from app.llm.client import get_llm_client
    from app.llm.fake import FakeLLMClient
    from app.main import app

    llm = FakeLLMClient({"email_subject": "s", "email_body": "b", "linkedin_note": "n", "highlights_used": []})
    app.dependency_overrides[get_llm_client] = lambda: llm
    try:
        with memory_client() as c:
            c.alice = create_account(c, "a2@example.com")
            login_as(c, c.alice)
            keep = _fact(c, "project", "Payments API in Go, 10k req/s", name="Payments API")
            _fact(c, "project", "Churn model in PyTorch, AUC 0.91", name="Churn")
            with app_db(c) as db:
                db.add(Company(id=1, name="Acme"))
                db.add(Job(job_id="j1", company_id=1, title="Backend", location="Pune", ghost_score=1, risk_band="Low",
                           legitimacy_probability=0.9, primary_skills_json="[]", raw_description_hash="h"))
                db.commit()
            v = c.post("/v1/profile/versions", json={"name": "Backend", "headline": "Go backend dev", "fact_ids": [keep]}).json()
            assert c.post("/api/jobs/j1/outreach", json={"version_id": v["id"]}).status_code == 200
            sent = llm.calls[0]["content"][0]["text"]
            assert "Payments API" in sent and "Churn" not in sent and "Go backend dev" in sent
            assert c.post("/api/jobs/j1/outreach", json={"version_id": 999}).status_code == 404
    finally:
        app.dependency_overrides.pop(get_llm_client, None)
