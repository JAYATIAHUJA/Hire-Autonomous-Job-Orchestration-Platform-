"""Auto-fill runs: plan from the profile, ask what's missing, show a review, send only on
the user's confirmation, and keep the pipeline card honest throughout."""

import pytest

from app.apply import runner
from app.apply.browser import FormResult
from app.apply.models import ApplyRun
from app.facts.models import AnswerBankEntry, ProfileFact, ResumeUpload
from app.facts.storage import InMemoryObjectStore, get_object_store
from app.jobs.models import Company, Job
from app.main import app
from auth_helpers import app_db, create_account, login_as, memory_client

SCHEMA = {"title": "Backend Engineer", "company_name": "Acme", "questions": [
    {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text"}]},
    {"label": "Last Name", "required": True, "fields": [{"name": "last_name", "type": "input_text"}]},
    {"label": "Email", "required": True, "fields": [{"name": "email", "type": "input_text"}]},
    {"label": "Resume/CV", "required": True, "fields": [{"name": "resume", "type": "input_file"}]},
    {"label": "What is your notice period?", "required": True, "fields": [{"name": "q_notice", "type": "input_text"}]},
    {"label": "Why Acme?", "required": True, "fields": [{"name": "q_why", "type": "textarea"}]},
]}


class FakeBrowser:
    def __init__(self, status="filled"):
        self.calls, self.status = [], status

    def __call__(self, form_url, answers, *, submit, on_action=None, screenshot_every=0, on_screenshot=None):
        self.calls.append({"url": form_url, "fields": {a.field_name: a.shown for a in answers}, "submit": submit})
        if on_action is not None:  # the real browser reports every field it fills
            for a in answers:
                on_action(a, True)
        status = ("submitted" if self.status == "filled" else self.status) if submit else "filled"
        return FormResult(status, [] if status in ("filled", "submitted") else ["blocked"], b"PNG")


@pytest.fixture
def env():
    store = InMemoryObjectStore()
    app.dependency_overrides[get_object_store] = lambda: store
    with memory_client() as c:
        c.store = store
        c.alice = create_account(c, "alice@example.com")
        login_as(c, c.alice)
        with app_db(c) as db:
            db.add(Company(id=1, name="Acme"))
            db.add(Job(job_id="gh1", company_id=1, title="Backend Engineer", location="Bengaluru", ghost_score=10,
                       risk_band="Low", legitimacy_probability=0.9, primary_skills_json="[]", raw_description_hash="h",
                       source="greenhouse", apply_url="https://boards.greenhouse.io/acme/jobs/123"))
            db.add(Job(job_id="lv1", company_id=1, title="Data Engineer", location="Pune", ghost_score=10,
                       risk_band="Low", legitimacy_probability=0.9, primary_skills_json="[]", raw_description_hash="h2",
                       source="lever", apply_url="https://jobs.lever.co/acme/1"))
            for kind, text in (("name", "Priya Sharma"),):
                db.add(ProfileFact(account_id=c.alice.id, kind=kind, text=text, structured={}, source="resume",
                                   status="approved"))
            db.add(ResumeUpload(account_id=c.alice.id, object_key="resumes/r.pdf", sha256="s", content_type="application/pdf",
                                size_bytes=3, text_source="text_layer"))
            db.add(AnswerBankEntry(account_id=c.alice.id, key="notice_period", value="30_days"))
            db.commit()
        store.put("resumes/r.pdf", b"%PDF", "application/pdf")
        c.session_factory = _session_factory(c)
        yield c
    app.dependency_overrides.pop(get_object_store, None)


def _session_factory(client):
    from app.db import get_db

    gen = app.dependency_overrides[get_db]

    def factory():
        it = gen()
        db = next(it)
        return db

    return factory


def _swipe(client, job_id):
    return client.post("/api/applications/swipe", json={"job_id": job_id, "direction": "right"}).json()["application"]


def _step(client, browser):
    return runner.process_next(client.session_factory, client.store, schema_fetcher=lambda url: SCHEMA,
                               form_runner=browser)


def test_the_whole_run_asks_reviews_and_sends_only_on_confirmation(env):
    card = _swipe(env, "gh1")
    assert card["can_autofill"] is True
    aid = card["application_id"]
    started = env.post(f"/api/applications/{aid}/autofill").json()
    assert started["status"] == "queued"
    assert env.get("/api/applications/board").json()["columns"][0]["cards"][0]["submission_status"] == "filling"

    browser = FakeBrowser()
    _step(env, browser)  # "Why Acme?" is required and unanswered: it asks, never guesses
    run = env.get(f"/api/applications/{aid}/autofill").json()
    assert run["status"] == "needs_answers" and [m["label"] for m in run["missing"]] == ["Why Acme?"]
    assert browser.calls == []

    env.post(f"/api/applications/{aid}/autofill/answers", json={"answers": {"Why Acme?": "Payments at scale."}})
    _step(env, browser)
    run = env.get(f"/api/applications/{aid}/autofill").json()
    assert run["status"] == "ready_to_submit" and run["has_screenshot"]
    fields = browser.calls[-1]["fields"]
    assert fields["first_name"] == "Priya" and fields["last_name"] == "Sharma" and fields["email"] == "alice@example.com"
    assert fields["q_notice"] == "30 days" and fields["q_why"] == "Payments at scale." and fields["resume"] == "resume.pdf"
    assert browser.calls[-1]["submit"] is False
    assert env.get(f"/api/applications/{aid}/autofill/screenshot").content == b"PNG"

    assert env.post(f"/api/applications/{aid}/autofill/submit", json={"company_name": "Acne"}).status_code == 422
    assert env.post(f"/api/applications/{aid}/autofill/submit", json={"company_name": "acme"}).json()["status"] == "submit_requested"
    _step(env, browser)
    assert browser.calls[-1]["submit"] is True
    assert env.get(f"/api/applications/{aid}/autofill").json()["status"] == "submitted"
    sent = env.get("/api/applications/board").json()["columns"][0]["cards"][0]
    assert sent["submission_status"] == "sent" and sent["submit_method"] == "auto"


def test_a_captcha_stops_the_run_and_nothing_counts_as_sent(env):
    aid = _swipe(env, "gh1")["application_id"]
    env.post(f"/api/applications/{aid}/autofill")
    with app_db(env) as db:
        db.query(ApplyRun).update({ApplyRun.extra_answers: {"Why Acme?": "x"}})
        db.commit()
    browser = FakeBrowser(status="captcha")
    _step(env, browser)
    env.post(f"/api/applications/{aid}/autofill/submit", json={"company_name": "Acme"})
    _step(env, browser)
    run = env.get(f"/api/applications/{aid}/autofill").json()
    assert run["status"] == "captcha"
    assert env.get("/api/applications/board").json()["columns"][0]["cards"][0]["submission_status"] == "failed"


def test_only_greenhouse_jobs_and_only_my_cards(env):
    aid = _swipe(env, "lv1")["application_id"]
    assert env.post(f"/api/applications/{aid}/autofill").status_code == 422
    gh = _swipe(env, "gh1")["application_id"]
    bob = create_account(env, "bob@example.com")
    login_as(env, bob)
    assert env.post(f"/api/applications/{gh}/autofill").status_code == 404
    assert env.get(f"/api/applications/{gh}/autofill/screenshot").status_code == 404


def test_cancel_puts_the_card_back(env):
    aid = _swipe(env, "gh1")["application_id"]
    env.post(f"/api/applications/{aid}/autofill")
    assert env.post(f"/api/applications/{aid}/autofill/cancel").json()["status"] == "cancelled"
    assert env.get("/api/applications/board").json()["columns"][0]["cards"][0]["submission_status"] == "not_sent"


def test_nothing_waiting_means_no_work():
    with memory_client() as c:
        assert runner.process_next(_session_factory(c), None, schema_fetcher=lambda u: SCHEMA, form_runner=FakeBrowser()) is None


def test_hidden_geo_fields_never_block_a_plan():
    """Real Greenhouse forms carry required latitude/longitude hidden fields; a person
    never types them, so they must not stop the plan (found on live GitLab/Capco runs)."""
    from app.apply.greenhouse import Applicant, JobRef, plan_application

    schema = {"title": "X", "company_name": "Acme", "questions": [
        {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text"}]},
        {"label": "Latitude", "required": True, "fields": [{"name": "lat", "type": "input_hidden"}]},
        {"label": "Longitude", "required": True, "fields": [{"name": "lng", "type": "input_hidden"}]},
    ]}
    ref = JobRef("acme", 1, "http://x/v1", "http://x/boards/acme/jobs/1", True)
    plan = plan_application(ref, schema, Applicant(first_name="A", last_name="B", email="a@b.co"))
    assert plan.ready and not plan.missing and not plan.unsupported


def test_careers_domain_links_resolve_from_the_job_id():
    """Employers wrap the Greenhouse form in their own domain (payoneer.com?gh_jid=);
    the board we ingested the job from still resolves it."""
    from app.apply.greenhouse import parse_job_url

    ref = parse_job_url("https://www.payoneer.com/careers/job/?gh_jid=8255852",
                        job_id="greenhouse_payoneer_8255852")
    assert (ref.board, ref.job_id, ref.is_mock) == ("payoneer", 8255852, False)
    with pytest.raises(ValueError):
        parse_job_url("https://www.payoneer.com/careers/job/?gh_jid=8255852")


def test_notice_period_topic_matches_the_wordings_real_forms_use():
    import re

    from app.apply.greenhouse import _norm
    from app.apply.runner import _TOPICS

    pattern = dict(_TOPICS)["notice_period"]
    for label in ("Notice period (days)", "How soon you can join us?", "How soon can you join?",
                  "Earliest start date?", "When can you start?"):
        assert re.search(pattern, _norm(label)), label
