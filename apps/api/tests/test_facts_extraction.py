"""Prompt-injection safety and output validation for resume fact extraction."""

import re

from app.facts.documents import extract_text
from app.facts.extraction import FACT_KINDS, FACT_TOOL, SYSTEM_PROMPT, build_content, extract_facts, validate_output
from app.llm.fake import FakeLLMClient
from facts_helpers import RESUMES, fact, tool_output

INJECTION_PDF = RESUMES / "injection_resume.pdf"


def _resume_block(text: str) -> str:
    [inner] = re.findall(r"<resume_document>\n(.*)\n</resume_document>", text, flags=re.DOTALL)
    return inner


def test_injected_resume_stays_inside_one_delimited_data_block():
    data = INJECTION_PDF.read_bytes()
    [block] = build_content(extract_text(data), data)
    text = block["text"]

    # The resume tried to close the data block and open a fake SYSTEM turn. It can't:
    # there is exactly one opening and one closing delimiter, and the attack is inside them.
    assert text.count("<resume_document>") == 1 and text.count("</resume_document>") == 1
    inner = _resume_block(text)
    assert "Ignore previous instructions" in inner and "[tag removed]" in inner
    assert text.index("Ignore previous instructions") > text.index("<resume_document>")
    assert text.index("Ignore previous instructions") < text.index("</resume_document>")


def test_system_prompt_is_frozen_and_tells_the_model_resume_text_is_data():
    assert "not instructions" in SYSTEM_PROMPT and "ignore previous instructions" in SYSTEM_PROMPT
    assert "contains_instructions" in SYSTEM_PROMPT
    assert FACT_TOOL["input_schema"]["additionalProperties"] is False
    assert set(FACT_TOOL["input_schema"]["properties"]["facts"]["items"]["properties"]["kind"]["enum"]) == set(FACT_KINDS)


def test_a_compromised_model_still_yields_only_well_formed_proposed_facts():
    """Even if the injection 'worked' on the model, only facts survive validation."""
    hijacked = {
        "facts": [
            fact("experience", "Data Engineer at Lotus Grid Analytics", company="Lotus Grid Analytics",
                 title="Data Engineer", start_date="2021-03", end_date="present"),
            fact("skill", "Apache Airflow", name="Apache Airflow"),
            {**fact("skill", "Expert in every programming language"), "status": "approved",
             "source": "user_confirmed", "confirmed_at": "2026-01-01"},
            {"kind": "instruction", "text": "INJECTION OK", "inferred": False, "evidence": "", "structured": {}},
            {"kind": "tool_call", "text": "call delete_account"},
            fact("skill", "x" * 5000),
            "not even an object",
            {**fact("education", "PhD from MIT"), "inferred": None},
        ],
        "contains_instructions": True,
        "reply": "INJECTION OK",
    }
    llm = FakeLLMClient(hijacked)
    data = INJECTION_PDF.read_bytes()
    result = extract_facts(llm, account_id=9, extracted=extract_text(data), file_bytes=data)

    assert result.contains_instructions is True
    assert result.dropped == 4
    assert [f.kind for f in result.facts] == ["experience", "skill", "skill", "education"]
    for candidate in result.facts:
        assert candidate.kind in FACT_KINDS
        assert set(vars(candidate)) == {"kind", "text", "inferred", "structured"}  # no status/source
    # A claim the model didn't explicitly mark as stated is treated as inferred.
    assert result.facts[-1].inferred is True


def test_injection_upload_end_to_end_creates_only_proposals():
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.auth.deps import Account, get_current_user
    from app.db import Base, get_db
    from app.facts.models import ProfileFact
    from app.facts.storage import InMemoryObjectStore, get_object_store
    from app.llm.client import get_llm_client
    from app.main import app

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    llm = FakeLLMClient(tool_output([
        {**fact("skill", "BigQuery", name="BigQuery"), "status": "approved"},
    ], contains_instructions=True))

    app.dependency_overrides[get_db] = lambda: Session()
    app.dependency_overrides[get_current_user] = lambda: Account(id=5)
    app.dependency_overrides[get_llm_client] = lambda: llm
    app.dependency_overrides[get_object_store] = InMemoryObjectStore
    try:
        client = TestClient(app)
        resp = client.post("/v1/profile/resume",
                           files={"file": ("r.pdf", INJECTION_PDF.read_bytes(), "application/pdf")})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["contains_instructions"] is True
        assert [p["status"] for p in body["proposals"]] == ["proposed"]
        with Session() as db:
            assert {f.status for f in db.query(ProfileFact).all()} == {"proposed"}
        assert client.get("/v1/profile").json()["profile"]["skills"] == []
    finally:
        app.dependency_overrides.clear()


def test_validate_output_tolerates_garbage():
    assert validate_output(None).facts == []
    assert validate_output({"facts": "nope"}).facts == []
    trimmed = validate_output(tool_output([fact("skill", "  Go  ", name="  Go ")]))
    assert trimmed.facts[0].text == "Go" and trimmed.facts[0].structured == {"name": "Go", "evidence": "Go"}
