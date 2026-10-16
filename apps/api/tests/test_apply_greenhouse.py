"""Greenhouse application planning: links, profile answers, and never guessing."""

import json

import pytest

from app.apply.greenhouse import (
    DISCLOSURE,
    Applicant,
    parse_job_url,
    plan_application,
    question_sheet,
    render_plan,
)


def _applicant(tmp_path, **overrides):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 test")
    data = {
        "first_name": "Asha",
        "last_name": "Rao",
        "email": "asha@example.com",
        "phone": "+91 98765 43210",
        "resume_path": str(resume),
        "linkedin": "https://linkedin.com/in/asha",
        "answers": {"Are you legally authorized to work in India?": "yes", "Notice period (days)": 30},
    }
    data.update(overrides)
    return Applicant(**data)


def _schema(*extra):
    return {
        "title": "Backend Engineer",
        "company_name": "Acme",
        "location": {"name": "Bengaluru, India"},
        "questions": [
            {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text"}]},
            {"label": "Last Name", "required": True, "fields": [{"name": "last_name", "type": "input_text"}]},
            {"label": "Email", "required": True, "fields": [{"name": "email", "type": "input_text"}]},
            {"label": "Phone", "required": False, "fields": [{"name": "phone", "type": "input_text"}]},
            {"label": "Resume/CV", "required": True, "fields": [
                {"name": "resume", "type": "input_file"}, {"name": "resume_text", "type": "textarea"}]},
            {"label": "LinkedIn Profile", "required": False, "fields": [{"name": "question_1", "type": "input_text"}]},
            {"label": "Are you legally authorized to work in India?", "required": True, "fields": [
                {"name": "question_2", "type": "multi_value_single_select",
                 "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}]},
            {"label": "Notice period (days)", "required": True, "fields": [{"name": "question_3", "type": "input_text"}]},
            *extra,
        ],
    }


JOB = parse_job_url("http://127.0.0.1:8180/boards/acme/jobs/4001")


@pytest.mark.parametrize(
    "url, board, job_id, form, mock",
    [
        ("https://boards.greenhouse.io/rubrik/jobs/4567", "rubrik", 4567, "https://job-boards.greenhouse.io/rubrik/jobs/4567", False),
        ("https://job-boards.greenhouse.io/Stripe/jobs/890/", "stripe", 890, "https://job-boards.greenhouse.io/stripe/jobs/890", False),
        ("https://boards.greenhouse.io/embed/job_app?for=okta&token=123", "okta", 123, "https://job-boards.greenhouse.io/okta/jobs/123", False),
        ("http://127.0.0.1:8180/boards/acme/jobs/4001", "acme", 4001, "http://127.0.0.1:8180/boards/acme/jobs/4001", True),
    ],
)
def test_job_links(url, board, job_id, form, mock):
    job = parse_job_url(url)
    assert (job.board, job.job_id, job.form_url, job.is_mock) == (board, job_id, form, mock)
    assert job.questions_url.endswith(f"/boards/{board}/jobs/{job_id}?questions=true")


@pytest.mark.parametrize("url", ["https://jobs.lever.co/cred/abc", "https://example.com/careers/1", "https://boards.greenhouse.io/acme"])
def test_unsupported_links_are_refused(url):
    with pytest.raises(ValueError):
        parse_job_url(url)


def test_a_complete_profile_fills_every_field(tmp_path):
    plan = plan_application(JOB, _schema(), _applicant(tmp_path))
    assert plan.ready
    got = {a.field_name: (a.value, a.shown) for a in plan.answers}
    assert got["first_name"] == ("Asha", "Asha")
    assert got["resume"][1] == "resume.pdf"
    assert got["question_1"][0] == "https://linkedin.com/in/asha"
    assert got["question_2"] == (1, "Yes")  # "yes" in the profile -> the "Yes" option
    assert got["question_3"] == ("30", "30")
    assert "resume_text" not in got  # the file answered it


def test_a_required_question_without_an_answer_is_never_guessed(tmp_path):
    extra = {"label": "Expected CTC (INR)", "required": True, "fields": [{"name": "question_9", "type": "input_text"}]}
    plan = plan_application(JOB, _schema(extra), _applicant(tmp_path))
    assert not plan.ready
    assert [m["label"] for m in plan.missing] == ["Expected CTC (INR)"]
    assert "question_9" not in {a.field_name for a in plan.answers}
    assert question_sheet(plan) == {"Expected CTC (INR)": ""}


def test_an_answer_that_is_not_one_of_the_options_is_asked_not_forced(tmp_path):
    applicant = _applicant(tmp_path, answers={"Are you legally authorized to work in India?": "Maybe", "Notice period (days)": "30"})
    plan = plan_application(JOB, _schema(), applicant)
    assert [m["label"] for m in plan.missing] == ["Are you legally authorized to work in India?"]
    assert plan.missing[0]["options"] == ["Yes", "No"]
    assert "Yes | No" in json.dumps(question_sheet(plan))


def test_optional_questions_without_an_answer_stay_blank(tmp_path):
    extra = {"label": "How did you hear about us?", "required": False, "fields": [{"name": "question_7", "type": "input_text"}]}
    plan = plan_application(JOB, _schema(extra), _applicant(tmp_path))
    assert plan.ready and "How did you hear about us?" in plan.skipped_optional


def test_disclosure_goes_in_an_additional_information_box_and_can_be_turned_off(tmp_path):
    extra = {"label": "Additional Information", "required": False, "fields": [{"name": "question_8", "type": "textarea"}]}
    on = plan_application(JOB, _schema(extra), _applicant(tmp_path))
    off = plan_application(JOB, _schema(extra), _applicant(tmp_path, disclosure=False))
    assert on.disclosure_field == "question_8"
    assert any(a.value == DISCLOSURE for a in on.answers)
    assert off.disclosure_field is None and all(a.value != DISCLOSURE for a in off.answers)


def test_unknown_required_field_types_block_the_run(tmp_path):
    extra = {"label": "Signature", "required": True, "fields": [{"name": "question_5", "type": "signature_pad"}]}
    applicant = _applicant(tmp_path, answers={**_applicant(tmp_path).answers, "Signature": "Asha Rao"})
    plan = plan_application(JOB, _schema(extra), applicant)
    assert not plan.ready and plan.unsupported == ["Signature (signature_pad)"]


def test_profile_problems_are_reported(tmp_path):
    assert _applicant(tmp_path).problems() == []
    bad = _applicant(tmp_path, email="not-an-email", resume_path=str(tmp_path / "missing.pdf"), first_name="")
    problems = " | ".join(bad.problems())
    assert "first_name" in problems and "email" in problems and "resume_path not found" in problems


def test_the_review_text_says_mock_or_real(tmp_path):
    plan = plan_application(JOB, _schema(), _applicant(tmp_path))
    assert "[MOCK ATS]" in render_plan(plan)
    real = plan_application(parse_job_url("https://boards.greenhouse.io/acme/jobs/1"), _schema(), _applicant(tmp_path))
    assert "[REAL EMPLOYER]" in render_plan(real)


def test_answer_bank_topics_answer_however_the_form_words_it(tmp_path):
    from app.apply.greenhouse import Applicant, JobRef, plan_application

    job = JobRef(board="acme", job_id=1, api_base="https://x", form_url="https://x/f", is_mock=False)
    schema = {"title": "SWE", "questions": [
        {"label": "What is your notice period?", "required": True, "fields": [{"name": "q1", "type": "input_text"}]},
        {"label": "Are you willing to relocate to Pune?", "required": True,
         "fields": [{"name": "q2", "type": "multi_value_single_select", "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}]},
    ]}
    applicant = Applicant(first_name="A", last_name="B", email="a@b.co",
                          topic_answers={r"notice period": "30 days", r"relocat": "Yes"})
    plan = plan_application(job, schema, applicant)
    assert plan.ready
    assert {a.field_name: a.shown for a in plan.answers} == {"q1": "30 days", "q2": "Yes"}
