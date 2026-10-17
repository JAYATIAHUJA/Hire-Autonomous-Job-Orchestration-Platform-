"""The same thing said differently across resumes must land once: alias and company
normalisation in the fact vault's dedupe keys."""

from app.facts.extraction import FactCandidate
from app.facts import repository
from auth_helpers import app_db, create_account, login_as, memory_client


def _propose(db, account_id, candidates, source_ref):
    return repository.create_proposals(
        db, account_id=account_id, source="resume", source_ref=source_ref,
        candidates=candidates, keep_pending=True,
    )


def test_skills_spelled_differently_are_one_skill():
    with memory_client() as client:
        account = create_account(client, "skills@example.com")
        login_as(client, account)
        with app_db(client) as db:
            first, skipped1 = _propose(db, account.id, [
                FactCandidate("skill", "Knows ReactJS", False, {"name": "ReactJS"}),
                FactCandidate("skill", "Knows JavaScript", False, {"name": "JavaScript"}),
                FactCandidate("skill", "Knows PostgreSQL", False, {"name": "Postgres"}),
            ], "resume-a")
            assert skipped1 == 0 and len(first) == 3
            for fact in first:
                fact.status = "approved"

            second, skipped2 = _propose(db, account.id, [
                FactCandidate("skill", "React for UI", False, {"name": "React"}),
                FactCandidate("skill", "JS", False, {"name": "JS"}),
                FactCandidate("skill", "PostgreSQL", False, {"name": "PostgreSQL"}),
                FactCandidate("skill", "Something new", False, {"name": "Kafka"}),
            ], "resume-b")
            assert skipped2 == 3  # react, js, postgresql are all repeats
            assert [f.structured["name"] for f in second] == ["Kafka"]
            for fact in second:
                fact.status = "approved"

            doc = repository.assemble(repository.facts_for(db, account.id, statuses=("approved",)), {})
            # The first resume's spelling wins; the later spellings were recognised as repeats.
            assert sorted(s["name"] for s in doc["skills"]) == ["JavaScript", "Kafka", "Postgres", "ReactJS"]


def test_companies_written_differently_are_one_role_and_bullets_attach():
    with memory_client() as client:
        account = create_account(client, "roles@example.com")
        login_as(client, account)
        with app_db(client) as db:
            first, _ = _propose(db, account.id, [
                FactCandidate("experience", "SDE at Zepto", False,
                              {"company": "Zepto", "title": "SDE", "start_date": "2023", "end_date": "present"}),
            ], "resume-a")
            for fact in first:
                fact.status = "approved"
            db.flush()

            second, skipped = _propose(db, account.id, [
                FactCandidate("experience", "SDE at Zepto (KiranaKart)", False,
                              {"company": "Zepto (KiranaKart)", "title": "SDE", "start_date": "2023",
                               "end_date": "present"}),
                FactCandidate("achievement", "Cut checkout latency by 40%", False,
                              {"company": "Zepto Software Pvt Ltd", "title": "SDE"}),
                FactCandidate("experience", "SDE at Razorpay", False,
                              {"company": "Razorpay Software Pvt Ltd", "title": "SDE", "start_date": "2021",
                               "end_date": "2022"}),
            ], "resume-b")
            assert skipped == 1  # the Zepto role again, in its longer spelling
            assert [f.kind for f in second] == ["achievement", "experience"]

            for fact in second:
                fact.status = "approved"
            db.flush()
            doc = repository.assemble(repository.facts_for(db, account.id, statuses=("approved",)), {})
            assert len(doc["experience"]) == 2  # Zepto once, Razorpay once
            zepto = next(e for e in doc["experience"] if "Zepto" in (e["company"] or ""))
            assert [b["text"] for b in zepto["bullets"]] == ["Cut checkout latency by 40%"]
            assert doc["achievements"] == []
