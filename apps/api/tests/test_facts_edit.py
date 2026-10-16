"""Correcting what the resume gave us, and adding what it missed."""

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


def _fact(client, kind, text, status="approved", **structured):
    with app_db(client) as db:
        fact = ProfileFact(account_id=client.alice.id, kind=kind, text=text, structured=structured,
                           source="resume", status=status, inferred=True)
        db.add(fact)
        db.commit()
        return fact.id


def test_editing_a_fact_changes_the_profile_and_marks_it_checked(client):
    fid = _fact(client, "experience", "SWE at Acme", company="Acme", title="SWE")
    resp = client.patch(f"/v1/profile/facts/{fid}", json={"text": "Software Engineer at Acme Fintech",
                                                          "structured": {"company": "Acme Fintech", "start_date": "2021-06"}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["inferred"] is False
    role = client.get("/v1/profile").json()["profile"]["experience"][0]
    assert (role["text"], role["company"], role["title"], role["start"]) == (
        "Software Engineer at Acme Fintech", "Acme Fintech", "SWE", "2021-06")


def test_a_proposed_fact_can_be_corrected_before_approving(client):
    fid = _fact(client, "skill", "Pythn", status="proposed")
    assert client.patch(f"/v1/profile/facts/{fid}", json={"text": "Python"}).json()["status"] == "proposed"
    client.post("/v1/profile/facts/approve", json={"ids": [fid]})
    assert [s["text"] for s in client.get("/v1/profile").json()["profile"]["skills"]] == ["Python"]


def test_adding_an_achievement_puts_it_under_its_role(client):
    _fact(client, "experience", "Backend engineer at Zepto", company="Zepto", title="Backend engineer")
    resp = client.post("/v1/profile/facts", json={"kind": "achievement", "text": "Cut checkout latency by 40%",
                                                  "structured": {"company": "Zepto", "title": "Backend engineer"}})
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "approved" and resp.json()["source"] == "user_confirmed"
    role = client.get("/v1/profile").json()["profile"]["experience"][0]
    assert [b["text"] for b in role["bullets"]] == ["Cut checkout latency by 40%"]


def test_adding_a_project_and_a_new_name(client):
    _fact(client, "name", "P. Sharma")
    client.post("/v1/profile/facts", json={"kind": "project", "text": "Hire: a job app", "structured": {"name": "Hire"}})
    client.post("/v1/profile/facts", json={"kind": "name", "text": "Priya Sharma"})
    profile = client.get("/v1/profile").json()["profile"]
    assert [p["name"] for p in profile["projects"]] == ["Hire"]
    assert profile["identity"]["name"]["value"] == "Priya Sharma"  # the old name is retired


@pytest.mark.parametrize("body", [{"kind": "favourite_food", "text": "dosa"}, {"kind": "skill", "text": ""}])
def test_bad_new_facts_are_422(client, body):
    assert client.post("/v1/profile/facts", json=body).status_code == 422


def test_cannot_edit_someone_elses_or_a_rejected_fact(client):
    fid = _fact(client, "skill", "Go")
    login_as(client, client.bob)
    assert client.patch(f"/v1/profile/facts/{fid}", json={"text": "Rust"}).status_code == 404
    login_as(client, client.alice)
    client.post("/v1/profile/facts/reject", json={"ids": [fid]})
    assert client.patch(f"/v1/profile/facts/{fid}", json={"text": "Rust"}).status_code == 404


def test_a_role_or_degree_without_company_or_institution_does_not_break_dedupe():
    # The model may leave company / institution null; that used to crash every upload.
    from app.facts.repository import dedupe_key

    assert dedupe_key("experience", "Freelance developer", {"start_date": "2022"}) == (
        "experience", "freelance developer", "2022", "")
    assert dedupe_key("education", "Class XII, CBSE", {}) == ("education", "class xii cbse", "", "")
    assert dedupe_key("experience", "SWE", {"company": "Acme", "title": "SWE"}) == ("experience", "acme", "swe", "", "")


@pytest.mark.parametrize("text,value", [
    ("Name is Aarav Mehta", "Aarav Mehta"),
    ("Candidate's name is Aarav Mehta.", "Aarav Mehta"),
    ("Phone: +91 90000 12345.", "+91 90000 12345"),
    ("Phone number is +91 90000 12345", "+91 90000 12345"),
    ("Located in Pune, India.", "Pune, India"),
    ("Email is a@b.co", "a@b.co"),
    ("Pune, India", "Pune, India"),
])
def test_single_facts_show_the_value_not_the_sentence(text, value):
    from app.facts.repository import single_value

    assert single_value(text) == value


def test_project_bullets_land_under_their_project_not_in_achievements(client):
    _fact(client, "project", "RailAlert: Telegram bot for train seats (Python, Redis)", name="RailAlert",
          url="https://github.com/a/railalert")
    _fact(client, "achievement", "Grew to 2,000 users in a month", name="RailAlert")
    _fact(client, "achievement", "Reached 99.9% uptime", name="railalert bot")  # wording differs a little
    _fact(client, "achievement", "Winner, Smart India Hackathon 2023")
    profile = client.get("/v1/profile").json()["profile"]
    project = profile["projects"][0]
    assert project["url"] == "https://github.com/a/railalert"
    assert [b["text"] for b in project["bullets"]] == ["Grew to 2,000 users in a month", "Reached 99.9% uptime"]
    assert [a["text"] for a in profile["achievements"]] == ["Winner, Smart India Hackathon 2023"]


def test_adding_a_pointer_to_a_project():
    with memory_client() as client:
        client.alice = create_account(client, "p@example.com")
        login_as(client, client.alice)
        client.post("/v1/profile/facts", json={"kind": "project", "text": "Hire", "structured": {"name": "Hire"}})
        client.post("/v1/profile/facts", json={"kind": "achievement", "text": "Shipped swipe deck",
                                               "structured": {"name": "Hire"}})
        assert [b["text"] for b in client.get("/v1/profile").json()["profile"]["projects"][0]["bullets"]] == [
            "Shipped swipe deck"]
