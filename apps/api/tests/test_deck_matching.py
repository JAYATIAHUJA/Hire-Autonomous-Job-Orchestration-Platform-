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
