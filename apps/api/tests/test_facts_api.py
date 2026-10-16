"""Resume upload -> proposals -> approve -> GET /v1/profile, with a fake LLM and store."""

import base64
import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.deps import Account, get_current_user
from app.db import Base, get_db
from app.facts import models as fact_models
from app.facts.extraction import SYSTEM_PROMPT, TOOL_NAME
from app.facts.storage import InMemoryObjectStore, get_object_store
from app.llm.client import LLMError, get_llm_client
from app.llm.fake import FakeLLMClient
from app.main import app
from facts_helpers import RESUMES, SAMPLE_FACTS, fact, tool_output

PDF = RESUMES / "sample_resume.pdf"


class Harness:
    def __init__(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.llm = FakeLLMClient(tool_output(SAMPLE_FACTS))
        self.store = InMemoryObjectStore()
        self.account = Account(id=1)

    def as_account(self, account_id: int):
        self.account = Account(id=account_id)

    def rows(self, model, account_id=None):
        with self.Session() as db:
            query = db.query(model)
            if account_id is not None:
                query = query.filter(model.account_id == account_id)
            return query.all()


@pytest.fixture
def h():
    harness = Harness()

    def override_db():
        db = harness.Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: harness.account
    app.dependency_overrides[get_llm_client] = lambda: harness.llm
    app.dependency_overrides[get_object_store] = lambda: harness.store
    harness.client = TestClient(app)
    yield harness
    app.dependency_overrides.clear()


def upload(h, path=PDF, data=None, name="resume.pdf"):
    payload = data if data is not None else path.read_bytes()
    return h.client.post("/v1/profile/resume", files={"file": (name, payload, "application/pdf")})


def approve(h, ids):
    return h.client.post("/v1/profile/facts/approve", json={"ids": ids})


def test_upload_proposes_facts_and_stores_the_file(h):
    resp = upload(h)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["sha256"] == hashlib.sha256(PDF.read_bytes()).hexdigest()
    assert body["text_source"] == "text_layer"
    assert len(body["proposals"]) == len(SAMPLE_FACTS)
    for proposal in body["proposals"]:
        assert proposal["status"] == "proposed"
        assert proposal["source"] == "resume"
        assert proposal["source_ref"] == body["upload_id"]
        assert proposal["confirmed_at"] is None
    inferred = [p for p in body["proposals"] if p["inferred"]]
    assert [p["text"] for p in inferred] == ["Distributed systems"]

    [(key, (data, content_type))] = h.store.objects.items()
    assert key.startswith("resumes/1/") and data == PDF.read_bytes() and content_type == "application/pdf"
    [upload_row] = h.rows(fact_models.ResumeUpload)
    assert upload_row.sha256 == body["sha256"] and upload_row.object_key == key

    [call] = h.llm.calls
    assert call["account_id"] == 1 and call["tool"]["name"] == TOOL_NAME
    assert call["system"] == SYSTEM_PROMPT  # nothing from the resume in the system prompt
    text = call["content"][0]["text"]
    assert "<resume_document>\nPriya Venkataraman" in text and text.count("</resume_document>") == 1


def test_nothing_reaches_the_profile_until_approved(h):
    proposals = upload(h).json()["proposals"]

    profile = h.client.get("/v1/profile").json()
    assert profile["profile"]["identity"]["name"] is None
    assert profile["profile"]["skills"] == []
    assert len(profile["pending_proposals"]) == len(proposals)

    by_text = {p["text"]: p["id"] for p in proposals}
    resp = approve(h, list(by_text.values()))
    assert resp.status_code == 200
    assert all(f["status"] == "approved" and f["confirmed_at"] for f in resp.json()["facts"])

    data = h.client.get("/v1/profile").json()
    profile = data["profile"]
    assert data["pending_proposals"] == []
    assert profile["identity"]["name"] == {"value": "Priya Venkataraman", "fact_id": by_text["Priya Venkataraman"]}
    assert [e["company"] for e in profile["experience"]] == ["Kestrel Logistics", "Tamarind Pay"]
    kestrel = profile["experience"][0]
    assert kestrel["start"] == "2023-01" and kestrel["end"] == "present"
    assert kestrel["bullets"] == [{
        "text": "Cut p95 latency of shipment tracking from 900 ms to 180 ms",
        "fact_id": by_text["Cut p95 latency of shipment tracking from 900 ms to 180 ms"],
        "inferred": False,
    }]
    assert {s["name"] for s in profile["skills"]} == {"Python", "Kafka", "Distributed systems"}
    assert profile["languages"][0]["level"] == "C1"
    assert profile["work_authorization"][0]["country"] == "India"
    assert profile["education"][0]["institution"] == "Coastal Institute of Technology"

    # The assembled profile is stored, too.
    [row] = h.rows(fact_models.CandidateProfile, 1)
    assert row.data["identity"]["name"]["value"] == "Priya Venkataraman"


def test_reject_keeps_a_fact_out_of_the_profile(h):
    proposals = upload(h).json()["proposals"]
    skill = next(p for p in proposals if p["text"] == "Kafka")
    resp = h.client.post("/v1/profile/facts/reject", json={"ids": [skill["id"]]})
    assert resp.status_code == 200 and resp.json()["facts"][0]["status"] == "rejected"
    approve(h, [p["id"] for p in proposals if p["id"] != skill["id"]])
    assert "Kafka" not in {s["name"] for s in h.client.get("/v1/profile").json()["profile"]["skills"]}


def test_reupload_diffs_against_approved_facts(h):
    approve(h, [p["id"] for p in upload(h).json()["proposals"]])
    old_location = next(f for f in h.rows(fact_models.ProfileFact) if f.kind == "location")

    h.llm.response = tool_output([
        fact("location", "Bengaluru, India"),        # conflicts with the approved Pune
        fact("skill", "Python", name="Python"),       # already approved: skipped
        fact("skill", "Go", name="Go"),               # new: additive
        fact("experience", "Senior Backend Engineer at Kestrel Logistics", company="Kestrel Logistics",
             title="Senior Backend Engineer", start_date="2022-06", end_date="present"),  # dates differ
    ])
    body = upload(h).json()
    assert body["skipped_duplicates"] == 1
    by_kind = {p["kind"]: p for p in body["proposals"]}
    assert set(by_kind) == {"location", "skill", "experience"}
    assert by_kind["location"]["conflict_with"] == old_location.id
    assert by_kind["location"]["conflict_with_text"] == "Pune, India"
    assert by_kind["skill"]["conflict_with"] is None
    assert by_kind["experience"]["conflict_with"] is not None

    # Approving the conflict replaces the old value.
    approve(h, [by_kind["location"]["id"]])
    profile = h.client.get("/v1/profile").json()["profile"]
    assert profile["identity"]["location"]["value"] == "Bengaluru, India"
    assert {f.id: f.status for f in h.rows(fact_models.ProfileFact)}[old_location.id] == "rejected"


def test_new_upload_replaces_previous_pending_proposals(h):
    first = upload(h).json()["proposals"]
    second = upload(h).json()["proposals"]
    assert len(second) == len(SAMPLE_FACTS)
    pending = h.client.get("/v1/profile").json()["pending_proposals"]
    assert {p["id"] for p in pending} == {p["id"] for p in second}
    assert approve(h, [first[0]["id"]]).status_code == 404


def test_another_account_cannot_touch_my_facts(h):
    ids = [p["id"] for p in upload(h).json()["proposals"]]
    h.as_account(2)
    assert approve(h, ids[:1]).status_code == 404
    assert h.client.post("/v1/profile/facts/reject", json={"ids": ids[:1]}).status_code == 404
    data = h.client.get("/v1/profile").json()
    assert data["pending_proposals"] == [] and data["profile"]["identity"]["name"] is None

    # A batch mixing my ids with someone else's fails as a whole, changing nothing.
    upload(h)
    own = [p.id for p in h.rows(fact_models.ProfileFact, 2)][:1]
    assert approve(h, own + ids[:1]).status_code == 404
    assert {f.status for f in h.rows(fact_models.ProfileFact, 2)} == {"proposed"}


def test_docx_upload(h):
    resp = upload(h, RESUMES / "sample_resume.docx", name="resume.docx")
    assert resp.status_code == 200, resp.text
    assert "Kestrel Logistics" in h.llm.calls[0]["content"][0]["text"]
    assert next(iter(h.store.objects)).endswith(".docx")


def test_empty_text_layer_sends_the_pdf_itself(h):
    from pypdf import PdfWriter

    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(buffer)
    scanned = buffer.getvalue()

    resp = upload(h, data=scanned)
    assert resp.status_code == 200, resp.text
    assert resp.json()["text_source"] == "pdf_document"
    document, instruction = h.llm.calls[0]["content"]
    assert document["type"] == "document"
    assert document["source"]["media_type"] == "application/pdf"
    assert base64.standard_b64decode(document["source"]["data"]) == scanned
    assert "data, not instructions" in instruction["text"]


@pytest.mark.parametrize(
    "data, status",
    [
        (b"", 400),
        (b"just some text, not a resume file", 415),
        (b"%PDF-1.4 truncated garbage", 422),
        (b"%PDF-" + b"0" * (5 * 1024 * 1024), 413),
    ],
    ids=["empty", "not-a-document", "broken-pdf", "too-large"],
)
def test_bad_uploads_are_refused_before_any_llm_call(h, data, status):
    assert upload(h, data=data).status_code == status
    assert h.llm.calls == [] and h.store.objects == {}


def test_llm_failure_keeps_nothing(h):
    h.llm.response = LLMError("upstream down")
    assert upload(h).status_code == 502
    assert h.store.objects == {}
    assert h.rows(fact_models.ResumeUpload) == [] and h.rows(fact_models.ProfileFact) == []


def test_upload_needs_configured_storage(h):
    app.dependency_overrides[get_object_store] = lambda: None
    assert upload(h).status_code == 503
    assert h.llm.calls == []


def test_answer_bank_round_trip(h):
    assert h.client.get("/v1/me/answer-bank").json() == {"answers": {}, "updated_at": None}
    resp = h.client.put("/v1/me/answer-bank", json={"answers": {"notice_period": "30 days", "expected_ctc": "28 LPA"}})
    assert resp.status_code == 200
    assert resp.json()["answers"] == {"expected_ctc": "28 LPA", "notice_period": "30 days"}

    # PUT replaces the whole bank.
    h.client.put("/v1/me/answer-bank", json={"answers": {"notice_period": "60 days"}})
    assert h.client.get("/v1/me/answer-bank").json()["answers"] == {"notice_period": "60 days"}

    h.as_account(2)
    assert h.client.get("/v1/me/answer-bank").json()["answers"] == {}


@pytest.mark.parametrize("answers", [{"Bad Key": "x"}, {"ok_key": "x" * 2001}])
def test_answer_bank_validation(h, answers):
    assert h.client.put("/v1/me/answer-bank", json={"answers": answers}).status_code == 422


def test_delete_profile_erases_everything_for_that_account_only(h):
    approve(h, [p["id"] for p in upload(h).json()["proposals"]])
    h.client.put("/v1/me/answer-bank", json={"answers": {"notice_period": "30 days"}})
    h.client.get("/v1/profile")
    h.as_account(2)
    upload(h)
    h.client.put("/v1/me/answer-bank", json={"answers": {"notice_period": "90 days"}})

    h.as_account(1)
    assert h.client.delete("/v1/profile").status_code == 204
    for model in (fact_models.ProfileFact, fact_models.CandidateProfile,
                  fact_models.AnswerBankEntry, fact_models.ResumeUpload):
        assert h.rows(model, 1) == []
    assert all(not key.startswith("resumes/1/") for key in h.store.objects)

    # Account 2 is untouched.
    assert len(h.rows(fact_models.ProfileFact, 2)) == len(SAMPLE_FACTS)
    assert [k for k in h.store.objects if k.startswith("resumes/2/")]
    h.as_account(2)
    assert h.client.get("/v1/me/answer-bank").json()["answers"] == {"notice_period": "90 days"}

    # Erasing an empty account is fine, even with no storage configured.
    h.as_account(3)
    app.dependency_overrides[get_object_store] = lambda: None
    assert h.client.delete("/v1/profile").status_code == 204


def test_delete_profile_keeps_rows_when_file_deletion_fails(h):
    upload(h)

    def broken_delete(key):
        raise OSError("s3 unavailable")

    h.store.delete = broken_delete
    assert h.client.delete("/v1/profile").status_code == 503
    assert len(h.rows(fact_models.ResumeUpload, 1)) == 1  # still there, so a retry can finish


def test_endpoints_require_login():
    client = TestClient(app)  # no dependency overrides: the WP1 placeholder refuses everyone
    for method, path in [("get", "/v1/profile"), ("delete", "/v1/profile"),
                         ("get", "/v1/me/answer-bank"), ("put", "/v1/me/answer-bank"),
                         ("post", "/v1/profile/facts/approve")]:
        kwargs = {"json": {"ids": ["x"], "answers": {}}} if method in {"put", "post"} else {}
        assert getattr(client, method)(path, **kwargs).status_code == 401, path
