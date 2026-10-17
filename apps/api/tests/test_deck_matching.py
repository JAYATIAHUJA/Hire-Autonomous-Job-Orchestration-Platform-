"""The deck puts jobs that fit the candidate's preferences first, and says why."""

from types import SimpleNamespace as Job

from app.jobs.matching import score

PREFS = {"roles": ["Backend engineer"], "locations": ["Bengaluru"], "remote_ok": True,
         "experience_band": "1-3", "deal_breakers": ["night shift"]}


def job(title, location="Pune", level="Not stated", remote=False, desc=""):
    return Job(title=title, location=location, experience_level=level, is_remote=remote, raw_description=desc)


def test_role_city_and_level_all_count_and_explain():
    points, reasons = score(job("Backend Engineer", "Bengaluru, India", "Entry-Level (0-2 yrs)"), PREFS)
    assert reasons == ["Matches Backend engineer", "In Bengaluru", "Fits 1–3 years"] and points == 7


def test_generic_words_alone_do_not_match_a_specific_role():
    assert score(job("Software Engineer", "Bengaluru"), PREFS)[1] == ["In Bengaluru"]


def test_remote_counts_when_the_candidate_is_open_to_it():
    assert "Remote" in score(job("Backend Developer", "Remote", remote=True), PREFS)[1]


def test_senior_roles_sink_for_juniors_and_deal_breakers_sink_further():
    good = score(job("Backend Engineer", "Bengaluru"), PREFS)[0]
    assert score(job("Staff Backend Engineer", "Bengaluru", "Senior (5+ yrs)"), PREFS)[0] < good
    assert score(job("Backend Engineer", "Bengaluru", desc="Rotational night shift"), PREFS)[0] < good


def test_no_preferences_no_signal():
    assert score(job("Backend Engineer"), None) == (0, [])


def test_the_deck_endpoint_ranks_by_preferences():
    from auth_helpers import create_account, login_as, memory_client

    with memory_client() as client:
        login_as(client, create_account(client, "d@example.com"))
        client.patch("/v1/me/preferences", json={"roles": ["Frontend engineer"], "locations": ["Hyderabad"],
                                                 "remote_ok": False})
        deck = client.get("/api/applications/deck?limit=50").json()
        assert deck["jobs"], "demo jobs are seeded in tests"
        first = deck["jobs"][0]
        assert first["match"]["score"] >= max(j["match"]["score"] for j in deck["jobs"])
        assert 0 <= first["match"]["percent"] <= 100
        assert any("In Hyderabad" in j["match"]["reasons"] for j in deck["jobs"])


def test_remote_from_india_beats_remote_from_abroad_and_percent_is_bounded():
    from app.jobs.matching import percent

    india = score(job("Backend Engineer", "Remote, Bengaluru, India", remote=True), {**PREFS, "locations": []})
    abroad = score(job("Backend Engineer", "Remote", remote=True), {**PREFS, "locations": []})
    assert india[0] > abroad[0] and "Remote, India" in india[1]
    assert percent(7) == 100 and percent(-3) == 0 and 0 < percent(4) < 100


def test_breaker_text_overrides_the_searched_text():
    # The deck scores thousands of rows with the description deferred; the caller
    # passes cheap text so deal-breakers still bite on the title and skills.
    clean = score(job("Backend Engineer", "Bengaluru"), PREFS, breaker_text="Backend Engineer []")[0]
    assert score(job("Backend Engineer", "Bengaluru"), PREFS, breaker_text="Backend Engineer night shift")[0] < clean
    # without an override the description is still searched, as single-job scoring relies on
    assert score(job("Backend Engineer", "Bengaluru", desc="Rotational night shift"), PREFS)[0] < clean


def test_deck_count_endpoint_counts_without_dealing_cards():
    from auth_helpers import create_account, login_as, memory_client

    with memory_client() as client:
        login_as(client, create_account(client, "count@example.com"))
        deck = client.get("/api/applications/deck?limit=5").json()
        counted = client.get("/api/applications/deck/count").json()
        assert counted["total"] == deck["total"] and counted["swiped_total"] == 0

        client.post("/api/applications/swipe", json={"job_id": deck["jobs"][0]["job_id"], "direction": "left"})
        after = client.get("/api/applications/deck/count").json()
        assert after["total"] == counted["total"] - 1 and after["swiped_total"] == 1


def test_ranked_deck_scores_on_cheap_columns_but_returns_descriptions():
    from datetime import datetime, timedelta, timezone

    from auth_helpers import app_db, create_account, login_as, memory_client
    from app.jobs import models as job_models

    with memory_client() as client:
        login_as(client, create_account(client, "desc@example.com"))
        client.patch("/v1/me/preferences", json={"roles": ["Backend engineer"], "locations": ["Bengaluru"]})
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with app_db(client) as db:
            db.add(job_models.Company(id=88001, name="Deferred Co"))
            db.add(job_models.Job(
                job_id="deferred-1", company_id=88001, title="Backend Engineer", location="Bengaluru, India",
                experience_level="Mid-Level (2-5 yrs)", ghost_score=10, risk_band="Low",
                legitimacy_probability=0.95, primary_skills_json='["python"]', raw_description_hash="dh",
                raw_description="Build payments APIs in Python. " * 40, source="greenhouse", is_active=True,
                posted_at=now - timedelta(days=1),
            ))
            db.commit()
        deck = client.get("/api/applications/deck?limit=50").json()
        card = next(j for j in deck["jobs"] if j["job_id"] == "deferred-1")
        # the page is re-fetched with its description and company after scoring on deferred rows
        assert "payments APIs" in (card["description"] or "")
        assert card["company"]["name"] == "Deferred Co"
