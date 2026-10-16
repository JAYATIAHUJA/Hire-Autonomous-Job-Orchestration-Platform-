"""Persistence for the fact vault: proposals, approvals, the assembled profile, the
answer bank and DPDP erasure. Every query is scoped to one ``account_id``."""

import datetime
import re
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from .extraction import FactCandidate
from .models import AnswerBankEntry, CandidateProfile, ProfileFact, ResumeUpload
from .schemas import FactOut
from .storage import ObjectStore

# Kinds a candidate has only one of: a differing new value conflicts with the approved one.
SINGLE_VALUED = {"name", "contact_email", "contact_phone", "location"}


class FactsNotFound(LookupError):
    """Some ids are not facts owned by this account (callers answer 404, never 403)."""


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _norm(value: Optional[str]) -> str:
    return " ".join(re.sub(r"[^\w@+]+", " ", (value or "").casefold()).split())


def _field(fact: Any, name: str) -> str:
    structured = fact.structured or {}
    return _norm(structured.get(name))


def dedupe_key(kind: str, text: str, structured: dict[str, Any]) -> tuple:
    """Two facts with the same key say the same thing."""
    if kind in {"skill", "language", "certification", "project"} and structured.get("name"):
        base = (kind, _norm(structured["name"]))
        return base + ((_norm(structured.get("level")),) if kind == "language" else ())
    if kind in {"experience", "education"}:
        return identity_key(kind, structured) + (
            _norm(structured.get("start_date")), _norm(structured.get("end_date")),
        )
    return (kind, _norm(text))


def identity_key(kind: str, structured: dict[str, Any]) -> Optional[tuple]:
    """Facts with the same identity but different values conflict. None: purely additive."""
    s = structured
    if kind in SINGLE_VALUED:
        return (kind,)
    if kind == "work_authorization":
        return (kind, _norm(s.get("country")))
    if kind == "language" and s.get("name"):
        return (kind, _norm(s.get("name")))
    if kind == "experience" and s.get("company"):
        return (kind, _norm(s.get("company")), _norm(s.get("title")))
    if kind == "education" and s.get("institution"):
        return (kind, _norm(s.get("institution")), _norm(s.get("degree")))
    return None


def to_out(fact: ProfileFact, by_id: Optional[dict[str, ProfileFact]] = None) -> FactOut:
    other = (by_id or {}).get(fact.conflict_with_fact_id) if fact.conflict_with_fact_id else None
    return FactOut(
        id=fact.id,
        kind=fact.kind,
        text=fact.text,
        structured=fact.structured or {},
        source=fact.source,
        source_ref=fact.source_ref,
        inferred=bool(fact.inferred),
        status=fact.status,
        conflict_with=fact.conflict_with_fact_id,
        conflict_with_text=other.text if other else None,
        confirmed_at=fact.confirmed_at,
    )


def facts_for(db: Session, account_id: int, statuses: Optional[Iterable[str]] = None) -> list[ProfileFact]:
    query = db.query(ProfileFact).filter(ProfileFact.account_id == account_id)
    if statuses is not None:
        query = query.filter(ProfileFact.status.in_(list(statuses)))
    return query.order_by(ProfileFact.created_at, ProfileFact.id).all()


def record_upload(db: Session, *, account_id: int, object_key: str, sha256: str, content_type: str,
                  size_bytes: int, text_source: str, upload_id: str) -> ResumeUpload:
    upload = ResumeUpload(id=upload_id, account_id=account_id, object_key=object_key, sha256=sha256,
                          content_type=content_type, size_bytes=size_bytes, text_source=text_source)
    db.add(upload)
    return upload


def create_proposals(db: Session, *, account_id: int, source: str, source_ref: str,
                     candidates: list[FactCandidate]) -> tuple[list[ProfileFact], int]:
    """Diff candidates against the vault. Returns (new proposals, skipped duplicates).

    A new upload replaces the previous upload's still-pending proposals: they were never
    trusted, and showing both would ask the user to review the same claims twice.
    """
    db.query(ProfileFact).filter(
        ProfileFact.account_id == account_id,
        ProfileFact.source == source,
        ProfileFact.status == "proposed",
    ).delete(synchronize_session=False)

    existing = facts_for(db, account_id, statuses=("approved", "rejected"))
    seen = {dedupe_key(f.kind, f.text, f.structured or {}) for f in existing}
    approved_by_identity: dict[tuple, ProfileFact] = {}
    for fact in existing:
        key = identity_key(fact.kind, fact.structured or {})
        if fact.status == "approved" and key is not None:
            approved_by_identity.setdefault(key, fact)

    created: list[ProfileFact] = []
    skipped = 0
    for candidate in candidates:
        key = dedupe_key(candidate.kind, candidate.text, candidate.structured)
        if key in seen:  # already approved, already rejected, or repeated in this resume
            skipped += 1
            continue
        seen.add(key)
        ident = identity_key(candidate.kind, candidate.structured)
        conflict = approved_by_identity.get(ident) if ident is not None else None
        fact = ProfileFact(
            account_id=account_id,
            kind=candidate.kind,
            text=candidate.text,
            structured=candidate.structured,
            source=source,
            source_ref=source_ref,
            inferred=candidate.inferred,
            status="proposed",
            conflict_with_fact_id=conflict.id if conflict else None,
        )
        db.add(fact)
        created.append(fact)
    db.flush()
    return created, skipped


def set_status(db: Session, account_id: int, ids: list[str], status: str) -> list[ProfileFact]:
    """Approve or reject facts. Approving a conflict retires the approved fact it contradicts."""
    wanted = list(dict.fromkeys(ids))
    facts = db.query(ProfileFact).filter(
        ProfileFact.account_id == account_id, ProfileFact.id.in_(wanted)
    ).all()
    if len(facts) != len(wanted):
        raise FactsNotFound()
    now = _utcnow()
    for fact in facts:
        if status == "approved":
            fact.status = "approved"
            fact.confirmed_at = fact.confirmed_at or now
            if fact.conflict_with_fact_id:
                old = db.query(ProfileFact).filter(
                    ProfileFact.account_id == account_id, ProfileFact.id == fact.conflict_with_fact_id
                ).first()
                if old is not None and old.status == "approved" and old.id not in wanted:
                    old.status = "rejected"
                    old.confirmed_at = None
        else:
            fact.status = "rejected"
            fact.confirmed_at = None
    db.flush()
    refresh_profile(db, account_id)
    order = {fact_id: i for i, fact_id in enumerate(wanted)}
    return sorted(facts, key=lambda f: order[f.id])


def _entry(fact: ProfileFact, **fields: Any) -> dict[str, Any]:
    entry = {name: (fact.structured or {}).get(name) for name in fields.get("names", ())}
    entry.update({"text": fact.text, "fact_id": fact.id, "inferred": bool(fact.inferred)})
    return entry


def assemble(facts: list[ProfileFact], preferences: dict[str, Any]) -> dict[str, Any]:
    """Build the profile document from approved facts only."""
    identity: dict[str, Any] = {"name": None, "email": None, "phone": None, "location": None, "links": []}
    single = {"name": "name", "contact_email": "email", "contact_phone": "phone", "location": "location"}
    data: dict[str, Any] = {
        "identity": identity, "work_authorization": [], "languages": [], "education": [],
        "experience": [], "achievements": [], "projects": [], "skills": [], "certifications": [],
        "preferences": preferences,
    }
    experience_by_key: dict[tuple, dict[str, Any]] = {}
    achievements: list[ProfileFact] = []
    for fact in facts:
        s = fact.structured or {}
        if fact.kind in single:
            identity[single[fact.kind]] = {"value": fact.text, "fact_id": fact.id}
        elif fact.kind == "link":
            identity["links"].append(_entry(fact, names=("url",)))
        elif fact.kind == "work_authorization":
            data["work_authorization"].append(_entry(fact, names=("country",)))
        elif fact.kind == "language":
            data["languages"].append(_entry(fact, names=("name", "level")))
        elif fact.kind == "education":
            data["education"].append(_entry(fact, names=("institution", "degree", "start_date", "end_date")))
        elif fact.kind == "experience":
            entry = {
                "company": s.get("company"), "title": s.get("title"),
                "start": s.get("start_date"), "end": s.get("end_date"),
                "text": fact.text, "fact_id": fact.id, "inferred": bool(fact.inferred), "bullets": [],
            }
            data["experience"].append(entry)
            experience_by_key.setdefault((_field(fact, "company"), _field(fact, "title")), entry)
        elif fact.kind == "achievement":
            achievements.append(fact)
        elif fact.kind == "project":
            data["projects"].append(_entry(fact, names=("name", "url")))
        elif fact.kind == "skill":
            data["skills"].append(_entry(fact, names=("name",)))
        elif fact.kind == "certification":
            data["certifications"].append(_entry(fact, names=("name",)))

    for fact in achievements:
        bullet = {"text": fact.text, "fact_id": fact.id, "inferred": bool(fact.inferred)}
        role = experience_by_key.get((_field(fact, "company"), _field(fact, "title")))
        if role is None:  # title wording often differs; fall back to the company alone
            role = next((e for (company, _), e in experience_by_key.items()
                         if company and company == _field(fact, "company")), None)
        (role["bullets"] if role else data["achievements"]).append(bullet)

    data["experience"].sort(key=lambda e: (e["start"] or ""), reverse=True)
    return data


def get_profile_row(db: Session, account_id: int) -> Optional[CandidateProfile]:
    return db.query(CandidateProfile).filter(CandidateProfile.account_id == account_id).first()


def refresh_profile(db: Session, account_id: int) -> CandidateProfile:
    row = get_profile_row(db, account_id)
    if row is None:
        row = CandidateProfile(account_id=account_id, data={})
        db.add(row)
    preferences = (row.data or {}).get("preferences") or {}
    row.data = assemble(facts_for(db, account_id, statuses=("approved",)), preferences)
    row.updated_at = _utcnow()
    db.flush()
    return row


def get_answer_bank(db: Session, account_id: int) -> list[AnswerBankEntry]:
    return db.query(AnswerBankEntry).filter(AnswerBankEntry.account_id == account_id).order_by(
        AnswerBankEntry.key
    ).all()


def replace_answer_bank(db: Session, account_id: int, answers: dict[str, str]) -> list[AnswerBankEntry]:
    current = {entry.key: entry for entry in get_answer_bank(db, account_id)}
    for key, entry in current.items():
        if key not in answers:
            db.delete(entry)
    for key, value in answers.items():
        entry = current.get(key)
        if entry is None:
            db.add(AnswerBankEntry(account_id=account_id, key=key, value=value))
        elif entry.value != value:
            entry.value = value
            entry.updated_at = _utcnow()
    db.flush()
    return get_answer_bank(db, account_id)


def erase_account_data(db: Session, account_id: int, store: Optional[ObjectStore]) -> None:
    """DPDP erasure: stored files first (so a storage failure leaves rows to retry), then rows."""
    uploads = db.query(ResumeUpload).filter(ResumeUpload.account_id == account_id).all()
    if uploads and store is None:
        raise RuntimeError("Stored resumes exist but file storage is not configured.")
    for upload in uploads:
        store.delete(upload.object_key)  # type: ignore[union-attr]
    # Clear self-references first so the delete never trips the FK on Postgres.
    db.query(ProfileFact).filter(ProfileFact.account_id == account_id).update(
        {ProfileFact.conflict_with_fact_id: None}, synchronize_session=False
    )
    for model in (ProfileFact, ResumeUpload, AnswerBankEntry, CandidateProfile):
        db.query(model).filter(model.account_id == account_id).delete(synchronize_session=False)
    db.flush()
