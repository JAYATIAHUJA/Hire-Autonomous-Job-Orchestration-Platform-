"""Auto-start on swipe, live run events, and answers remembered across forms."""

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.apply import runner, service
from app.apply.browser import FormResult
from app.apply.greenhouse import remembered_match
from app.apply.models import ApplyRun, ApplyRunEvent
from app.db import Base
from app.facts.models import AnswerBankEntry, ProfileFact, ResumeUpload
from app.facts.storage import InMemoryObjectStore, get_object_store
from app.jobs.models import Company, Job
from app.main import app
from auth_helpers import app_db, create_account, login_as, memory_client

# Both forms ask the same thing in different words; only that question is required.
SCHEMA_A = {"title": "Backend Engineer", "company_name": "Acme", "questions": [
    {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text"}]},
    {"label": "Last Name", "required": True, "fields": [{"name": "last_name", "type": "input_text"}]},
    {"label": "Email", "required": True, "fields": [{"name": "email", "type": "input_text"}]},
    {"label": "Resume/CV", "required": True, "fields": [{"name": "resume", "type": "input_file"}]},
    {"label": "How did you hear about us?", "required": True,
     "fields": [{"name": "q_hear", "type": "input_text"}]},
]}
SCHEMA_B = {**SCHEMA_A, "company_name": "Beta", "questions": [
    {**q, "label": "How did you hear about this role?"} if q["label"] == "How did you hear about us?" else q
    for q in SCHEMA_A["questions"]
]}


class FakeBrowser:
    def __init__(self):
        self.calls = []

    def __call__(self, form_url, answers, *, submit, on_action=None, screenshot_every=0, on_screenshot=None):
        self.calls.append({"url": form_url, "fields": {a.field_name: a.shown for a in answers}, "submit": submit})
        if on_action is not None:
            for a in answers:
                on_action(a, True)
        return FormResult("submitted" if submit else "filled", [], b"PNG")


def _schema_for(url):
    return SCHEMA_A if "/acme/" in url else SCHEMA_B


@pytest.fixture
def env():
    store = InMemoryObjectStore()
    app.dependency_overrides[get_object_store] = lambda: store
    with memory_client() as c:
        c.store = store
        c.alice = create_account(c, "auto@example.com")
        login_as(c, c.alice)
        with app_db(c) as db:
            db.add(Company(id=1, name="Acme"))
            db.add(Company(id=2, name="Beta"))
            db.add(Job(job_id="gh1", company_id=1, title="Backend Engineer", location="Bengaluru", ghost_score=10,
                       risk_band="Low", legitimacy_probability=0.9, primary_skills_json="[]",
                       raw_description_hash="h", source="greenhouse",
                       apply_url="https://boards.greenhouse.io/acme/jobs/1"))
            db.add(Job(job_id="gh2", company_id=2, title="Backend Engineer", location="Pune", ghost_score=10,
                       risk_band="Low", legitimacy_probability=0.9, primary_skills_json="[]",
                       raw_description_hash="h2", source="greenhouse",
                       apply_url="https://boards.greenhouse.io/beta/jobs/2"))
            db.add(Job(job_id="lv1", company_id=1, title="Data Engineer", location="Pune", ghost_score=10,
                       risk_band="Low", legitimacy_probability=0.9, primary_skills_json="[]", raw_description_hash="h3",
                       source="lever", apply_url="https://jobs.lever.co/acme/1"))
            db.add(ProfileFact(account_id=c.alice.id, kind="name", text="Priya Sharma", structured={}, source="resume",
                               status="approved"))
            db.add(ResumeUpload(account_id=c.alice.id, object_key="resumes/r.pdf", sha256="s",
                                content_type="application/pdf", size_bytes=3, text_source="text_layer"))
            db.commit()
        store.put("resumes/r.pdf", b"%PDF", "application/pdf")
        c.browser = FakeBrowser()
        c.session_factory = _session_factory(c)
        yield c
    app.dependency_overrides.pop(get_object_store, None)


def _session_factory(client):
    from app.db import get_db

    gen = app.dependency_overrides[get_db]

    def factory():
        return next(gen())

    return factory


def _step(env):
    return runner.process_next(env.session_factory, env.store, schema_fetcher=_schema_for,
                               form_runner=env.browser)


def _swipe(env, job_id, direction="right"):
    return env.post("/api/applications/swipe", json={"job_id": job_id, "direction": direction}).json()


def test_a_right_swipe_starts_the_run_on_its_own(env):
    resp = _swipe(env, "gh1")
    assert resp["autofill_started"] is True
    assert resp["application"]["autofill"]["status"] == "queued"
    assert env.get(f"/api/applications/{resp['application']['application_id']}/autofill").json()["status"] == "queued"
    card = env.get("/api/applications/board").json()["columns"][0]["cards"][0]
    assert card["submission_status"] == "filling" and card["autofill"]["status"] == "queued"


def test_the_setting_turns_auto_start_off_and_manual_still_works(env):
    env.patch("/v1/me/preferences", json={"autofill_on_swipe": False})
    assert env.get("/v1/me/preferences").json()["autofill_on_swipe"] is False
    resp = _swipe(env, "gh1")
    assert resp["autofill_started"] is False and resp["application"]["autofill"] is None
    aid = resp["application"]["application_id"]
    assert env.post(f"/api/applications/{aid}/autofill").json()["status"] == "queued"


def test_left_swipes_and_unsupported_boards_never_start(env):
    assert _swipe(env, "lv1")["autofill_started"] is False
    left = _swipe(env, "gh2", "left")
    assert left["autofill_started"] is False and left["application"]["autofill"] is None


def test_events_stream_the_run_and_after_skips_old_ones(env):
    aid = _swipe(env, "gh1")["application"]["application_id"]
    _step(env)  # asks the one required question it can't answer
    feed = env.get(f"/api/applications/{aid}/autofill/events").json()
    kinds = [e["kind"] for e in feed["events"]]
    assert kinds[0] == "queued" and "step" in kinds and "missing" in kinds
    assert feed["status"] == "needs_answers"
    tail = env.get(f"/api/applications/{aid}/autofill/events",
                   params={"after": feed["events"][-1]["seq"]}).json()
    assert tail["events"] == []
    env.post(f"/api/applications/{aid}/autofill/answers", json={"answers": {"How did you hear about us?": "Campus placement"}})
    _step(env)
    feed2 = env.get(f"/api/applications/{aid}/autofill/events").json()
    labels = [e["label"] for e in feed2["events"]]
    assert any(l.startswith("You answered") for l in labels)
    assert any(l.startswith("Filled") or l.startswith("Uploaded") for l in labels)
    assert feed2["events"][-1]["kind"] == "ready"
    only_new = env.get(f"/api/applications/{aid}/autofill/events",
                       params={"after": feed["events"][-1]["seq"]}).json()
    assert [e["seq"] for e in only_new["events"]] == [e["seq"] for e in feed2["events"][len(feed["events"]):]]


def test_an_answer_is_remembered_and_reused_in_other_words(env):
    first = _swipe(env, "gh1")["application"]["application_id"]
    _step(env)
    env.post(f"/api/applications/{first}/autofill/answers",
             json={"answers": {"How did you hear about us?": "Campus placement"}})
    _step(env)
    assert env.get(f"/api/applications/{first}/autofill").json()["status"] == "ready_to_submit"

    memory = env.get("/v1/me/answer-memory").json()
    assert len(memory) == 1 and memory[0]["question"] == "How did you hear about us?"
    assert memory[0]["answer"] == "Campus placement"

    # A different company asks the same thing in other words: filled, not asked again.
    second = _swipe(env, "gh2")["application"]["application_id"]
    _step(env)
    run = env.get(f"/api/applications/{second}/autofill").json()
    assert run["status"] == "ready_to_submit"
    heard = next(f for f in run["filled"] if f["label"] == "How did you hear about this role?")
    assert heard["shown"] == "Campus placement" and heard["source"] == "remembered"
    assert env.get("/v1/me/answer-memory").json()[0]["uses"] == 1


def test_remembered_answers_never_fill_free_text_or_mismatched_sensitive_questions():
    assert remembered_match({"why do you want to work here": "Because"}, "Why do you want to join us?") is None
    # Sensitive: near-identical wording is not enough, identical is.
    assert remembered_match({"what is your current ctc": "10L"}, "What is your expected CTC?") is None
    assert remembered_match({"what is your current ctc": "10L"}, "What is your CURRENT ctc?") is not None
    # A different question with shared filler words doesn't match.
    assert remembered_match({"how did you hear about us": "Campus"}, "What is your notice period?") is None


def test_memory_can_be_edited_and_deleted(env):
    aid = _swipe(env, "gh1")["application"]["application_id"]
    _step(env)
    env.post(f"/api/applications/{aid}/autofill/answers",
             json={"answers": {"How did you hear about us?": "Campus placement"}})
    entry = env.get("/v1/me/answer-memory").json()[0]
    edited = env.patch(f"/v1/me/answer-memory/{entry['id']}", json={"answer": "A friend"})
    assert edited.json()["answer"] == "A friend"
    assert env.delete(f"/v1/me/answer-memory/{entry['id']}").status_code == 204
    assert env.get("/v1/me/answer-memory").json() == []


def test_the_board_counts_applications_waiting_on_the_user(env):
    assert env.get("/api/applications/board").json()["needs_you"] == 0
    _swipe(env, "gh1")
    _step(env)  # lands on needs_answers
    assert env.get("/api/applications/board").json()["needs_you"] == 1


def test_events_get_gap_free_seq_without_autoflush():
    # Production sessions don't autoflush; emit must still hand out 1, 2, 3...
    # (found against Postgres, where equal seqs violate the unique constraint.)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    run = ApplyRun(account_id=1, application_id="app_x", job_id="j", status="queued")
    db.add(run)
    db.flush()
    for i in range(3):
        service.emit(db, run, "step", f"step {i}")
    db.commit()
    seqs = [r[0] for r in db.query(ApplyRunEvent.seq).order_by(ApplyRunEvent.seq).all()]
    assert seqs == [1, 2, 3]


def test_a_crashed_filling_run_is_reclaimed_and_an_interrupted_send_is_never_replayed(env):
    aid = _swipe(env, "gh1")["application"]["application_id"]
    with app_db(env) as db:  # the worker died mid-fill five minutes ago
        run = db.query(ApplyRun).one()
        run.status, run.updated_at = "filling", datetime.datetime.now() - datetime.timedelta(minutes=6)
        db.commit()
    _step(env)  # reclaimed and processed
    assert env.get(f"/api/applications/{aid}/autofill").json()["status"] == "needs_answers"

    with app_db(env) as db:  # and a send that died is requeued, not replayed
        run = db.query(ApplyRun).one()
        run.status, run.updated_at = "submitting", datetime.datetime.now() - datetime.timedelta(minutes=6)
        db.commit()
    assert runner.process_next(env.session_factory, env.store, schema_fetcher=_schema_for,
                               form_runner=env.browser) is None
    assert env.get(f"/api/applications/{aid}/autofill").json()["status"] == "queued"


def test_the_handoff_can_download_the_resume(env):
    """A CAPTCHA run hands off to the user: the answers live on the run, the resume
    file must come back out of storage for them to attach by hand."""
    r = env.get("/v1/profile/resume/latest")
    assert r.status_code == 200 and r.content == b"%PDF"
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.headers["content-disposition"].startswith('attachment; filename="resume.pdf"')


def test_no_resume_uploaded_answers_404_cleanly(env):
    with app_db(env) as db:
        from app.facts.models import ResumeUpload
        db.query(ResumeUpload).filter(ResumeUpload.account_id == env.alice.id).delete()
        db.commit()
    assert env.get("/v1/profile/resume/latest").status_code == 404
