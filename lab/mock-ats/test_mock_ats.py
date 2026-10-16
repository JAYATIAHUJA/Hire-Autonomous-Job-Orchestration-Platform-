from fastapi.testclient import TestClient

from mock_ats import SUBMISSIONS, app

client = TestClient(app)


def test_board_lists_jobs_with_hosted_form_urls():
    jobs = client.get("/v1/boards/acme/jobs").json()["jobs"]
    assert [j["id"] for j in jobs] == [4001, 4002]
    assert jobs[0]["absolute_url"].endswith("/boards/acme/jobs/4001")


def test_questions_and_hosted_form_agree():
    questions = client.get("/v1/boards/acme/jobs/4001?questions=true").json()["questions"]
    html = client.get("/boards/acme/jobs/4001").text
    for q in questions:
        assert f'name="{q["fields"][0]["name"]}"' in html


def test_submit_records_and_rejects_missing_required_fields():
    SUBMISSIONS.clear()
    bad = client.post("/boards/acme/jobs/4001/apply", data={"first_name": "Ana"})
    assert bad.status_code == 422

    ok = client.post(
        "/boards/acme/jobs/4001/apply",
        data={"first_name": "Ana", "last_name": "Rao", "email": "ana@example.com",
              "question_1002": "1", "question_1003": "30"},
        files={"resume": ("resume.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert ok.status_code == 200
    assert "application_confirmation" in ok.text
    assert client.get("/_submissions").json()["submissions"][0]["fields"]["resume"] == "resume.pdf"
