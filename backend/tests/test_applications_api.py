import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.applications import models as application_models  # noqa: F401
from app.db import Base, get_db
from app.jobs import models as job_models  # noqa: F401
from app.main import app

CANDIDATE = "oshisharma1222"


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def swipe_right(client, job_id: str):
    return client.post(
        "/api/applications/swipe",
        json={"job_id": job_id, "direction": "right", "candidate_ref": CANDIDATE},
    )


def test_deck_serves_ghost_filtered_cards(client):
    resp = client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}&limit=10")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] > 0
    job_ids = {job["job_id"] for job in data["jobs"]}
    # The ghost fixtures must never reach the swipe deck.
    assert "ghost_corp_005" not in job_ids
    assert "ghost_harvest_006" not in job_ids


def test_swipe_right_writes_a_signed_consent_log(client):
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")

    resp = swipe_right(client, "blr_swig_001")
    assert resp.status_code == 200
    body = resp.json()

    assert body["already_recorded"] is False
    assert body["application"]["stage"] == "applied"
    assert body["application"]["stage_label"] == "Applied"

    consent = body["consent"]
    assert consent["verified"] is True
    assert consent["algorithm"] == "HMAC-SHA256"
    assert consent["employer_name"] == "Swiggy Engineering"
    assert consent["subject"] == CANDIDATE
    assert consent["purpose"]
    assert consent["granted_at"]
    assert consent["payload"]["job_id"] == "blr_swig_001"

    # The receipt is readable and re-verified on its own endpoint.
    application_id = body["application"]["application_id"]
    receipt = client.get(f"/api/applications/{application_id}/consent")
    assert receipt.status_code == 200
    assert receipt.json()["consent_id"] == consent["consent_id"]
    assert receipt.json()["verified"] is True


def test_swiping_the_same_card_twice_does_not_issue_a_second_consent(client):
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")

    first = swipe_right(client, "blr_swig_001").json()
    second = swipe_right(client, "blr_swig_001").json()

    assert second["already_recorded"] is True
    assert second["consent"]["consent_id"] == first["consent"]["consent_id"]


def test_swipe_left_skips_the_card_without_consent(client):
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")

    resp = client.post(
        "/api/applications/swipe",
        json={"job_id": "hyd_zepto_002", "direction": "left", "candidate_ref": CANDIDATE},
    )
    assert resp.status_code == 200
    assert resp.json()["consent"] is None
    assert resp.json()["application"]["stage"] == "skipped"

    application_id = resp.json()["application"]["application_id"]
    assert client.get(f"/api/applications/{application_id}/consent").status_code == 404

    # A skipped card leaves the deck but never appears on the board.
    deck = client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}").json()
    assert "hyd_zepto_002" not in {job["job_id"] for job in deck["jobs"]}

    board = client.get(f"/api/applications/board?candidate_ref={CANDIDATE}").json()
    assert board["total"] == 0


def test_deck_stays_a_full_page_as_the_candidate_swipes(client):
    first = client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}&limit=3").json()
    assert len(first["jobs"]) == 3

    for job in first["jobs"]:
        client.post(
            "/api/applications/swipe",
            json={"job_id": job["job_id"], "direction": "left", "candidate_ref": CANDIDATE},
        )

    # Exclusion happens in SQL, so the next page is still full rather than short.
    second = client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}&limit=3").json()
    assert len(second["jobs"]) == 3
    assert not {job["job_id"] for job in second["jobs"]} & {job["job_id"] for job in first["jobs"]}


def test_deck_is_per_candidate(client):
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")
    client.post(
        "/api/applications/swipe",
        json={"job_id": "blr_swig_001", "direction": "right", "candidate_ref": CANDIDATE},
    )

    mine = client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}").json()
    theirs = client.get("/api/applications/deck?candidate_ref=someone-else").json()

    assert "blr_swig_001" not in {job["job_id"] for job in mine["jobs"]}
    assert "blr_swig_001" in {job["job_id"] for job in theirs["jobs"]}
    assert client.get("/api/applications/board?candidate_ref=someone-else").json()["total"] == 0


def test_events_are_returned_in_the_order_they_happened(client):
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")
    application_id = swipe_right(client, "blr_swig_001").json()["application"]["application_id"]

    client.post(f"/api/applications/{application_id}/stage", json={"to_stage": "interview_scheduled"})
    client.post(f"/api/applications/{application_id}/stage", json={"to_stage": "rejected"})
    client.post(f"/api/applications/{application_id}/stage", json={"to_stage": "applied"})

    stages = [event["to_stage"] for event in client.get(f"/api/applications/{application_id}").json()["events"]]
    assert stages == ["applied", "interview_scheduled", "rejected", "applied"]


def test_swipe_rejects_unknown_job_and_bad_direction(client):
    assert swipe_right(client, "does_not_exist").status_code == 404

    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")
    bad = client.post(
        "/api/applications/swipe",
        json={"job_id": "blr_swig_001", "direction": "up", "candidate_ref": CANDIDATE},
    )
    assert bad.status_code == 422


def test_board_has_the_three_pipeline_columns(client):
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")
    swipe_right(client, "blr_swig_001")

    board = client.get(f"/api/applications/board?candidate_ref={CANDIDATE}").json()
    assert [column["stage"] for column in board["columns"]] == ["applied", "interview_scheduled", "rejected"]
    assert [column["label"] for column in board["columns"]] == ["Applied", "Interview Scheduled", "Rejected"]
    assert board["columns"][0]["count"] == 1
    assert board["total"] == 1


def test_recruiter_reply_moves_the_card_from_applied_to_interview(client):
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")
    application_id = swipe_right(client, "blr_swig_001").json()["application"]["application_id"]

    sync = client.post(
        "/api/mail/sync",
        json={
            "messages": [
                {
                    "uid": "1001",
                    "from_address": "Talent Team <careers@swiggy.com>",
                    "subject": "Interview invitation - Backend Software Engineer",
                    "body": "We would like to invite you to a technical interview. Please share your availability.",
                }
            ]
        },
    )
    assert sync.status_code == 200
    stats = sync.json()
    assert stats["source"] == "inline"
    assert stats["matched"] == 1
    assert stats["moved"] == 1

    card = client.get(f"/api/applications/{application_id}").json()
    assert card["stage"] == "interview_scheduled"
    assert card["events"][-1]["source"] == "imap"

    board = client.get(f"/api/applications/board?candidate_ref={CANDIDATE}").json()
    assert board["columns"][1]["count"] == 1


def test_rejection_reply_moves_the_card_and_is_not_replayed(client):
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")
    application_id = swipe_right(client, "pune_cred_003").json()["application"]["application_id"]

    message = {
        "uid": "2002",
        "from_address": "hiring@cred.club",
        "subject": "Update on your CRED application",
        "body": "We regret to inform you that we have decided to move forward with other candidates.",
    }

    first = client.post("/api/mail/sync", json={"messages": [message]}).json()
    assert first["moved"] == 1
    assert client.get(f"/api/applications/{application_id}").json()["stage"] == "rejected"

    # The same uid arriving again is ignored rather than re-applied.
    second = client.post("/api/mail/sync", json={"messages": [message]}).json()
    assert second["moved"] == 0
    assert second["skipped"] == 1


def test_unrelated_mail_leaves_the_board_untouched(client):
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")
    application_id = swipe_right(client, "blr_swig_001").json()["application"]["application_id"]

    stats = client.post(
        "/api/mail/sync",
        json={
            "messages": [
                {
                    "uid": "3003",
                    "from_address": "news@unrelated.io",
                    "subject": "Your weekly newsletter",
                    "body": "Here are this week's engineering blog posts.",
                }
            ]
        },
    ).json()

    assert stats["moved"] == 0
    assert client.get(f"/api/applications/{application_id}").json()["stage"] == "applied"


def test_candidate_can_move_a_card_by_hand(client):
    client.get(f"/api/applications/deck?candidate_ref={CANDIDATE}")
    application_id = swipe_right(client, "blr_swig_001").json()["application"]["application_id"]

    moved = client.post(
        f"/api/applications/{application_id}/stage",
        json={"to_stage": "interview_scheduled", "detail": "Recruiter called instead of emailing."},
    )
    assert moved.status_code == 200
    assert moved.json()["stage"] == "interview_scheduled"
    assert moved.json()["events"][-1]["source"] == "manual"

    bad_stage = client.post(f"/api/applications/{application_id}/stage", json={"to_stage": "hired"})
    assert bad_stage.status_code == 422


def test_mail_sync_without_a_mailbox_configured_reports_503(client):
    resp = client.post("/api/mail/sync", json={})
    assert resp.status_code == 503
    assert "IMAP_HOST" in resp.json()["detail"]
