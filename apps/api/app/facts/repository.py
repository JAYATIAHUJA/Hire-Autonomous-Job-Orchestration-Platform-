"""Persistence for the fact vault: proposals, approvals, the assembled profile, the
answer bank and DPDP erasure. Every query is scoped to one ``account_id``."""

import datetime
import re
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from .extraction import FactCandidate
from .models import AnswerBankEntry, CandidateProfile, ProfileFact, ProfileVersion, ResumeUpload
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


_FREE_TEXT_KINDS = ("achievement", "project")
_STOP = {"a", "an", "the", "and", "or", "of", "to", "in", "at", "for", "with", "on", "by", "from", "that", "which"}


def _words(text: str) -> set[str]:
    return {w for w in _norm(text).split() if w not in _STOP}


def _similar(a: set[str], b: set[str]) -> bool:
    """Same claim in other words: most of the shorter one's words appear in the other."""
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.75


def dedupe_key(kind: str, text: str, structured: dict[str, Any]) -> tuple:
    """Two facts with the same key say the same thing."""
    if kind in {"skill", "language", "certification", "project"} and structured.get("name"):
        base = (kind, _norm(structured["name"]))
        return base + ((_norm(structured.get("level")),) if kind == "language" else ())
    if kind in {"experience", "education"}:
        # Without a company / institution there is no identity: fall back to the wording.
        ident = identity_key(kind, structured) or (kind, _norm(text))
        return ident + (_norm(structured.get("start_date")), _norm(structured.get("end_date")))
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
                     candidates: list[FactCandidate], keep_pending: bool = False) -> tuple[list[ProfileFact], int]:
    """Diff candidates against the vault. Returns (new proposals, skipped duplicates).

    A new upload replaces the previous upload's still-pending proposals: they were never
    trusted, and showing both would ask the user to review the same claims twice. With
    ``keep_pending`` (several resumes uploaded together) they stay, and this upload's
    claims that repeat them are skipped instead.
    """
    if not keep_pending:
        db.query(ProfileFact).filter(
            ProfileFact.account_id == account_id,
            ProfileFact.source == source,
            ProfileFact.status == "proposed",
        ).delete(synchronize_session=False)

    existing = facts_for(db, account_id, statuses=("approved", "rejected", "proposed") if keep_pending
                         else ("approved", "rejected"))
    seen = {dedupe_key(f.kind, f.text, f.structured or {}) for f in existing}
    approved_by_identity: dict[tuple, ProfileFact] = {}
    for fact in existing:
        key = identity_key(fact.kind, fact.structured or {})
        if fact.status == "approved" and key is not None:
            approved_by_identity.setdefault(key, fact)

    # Two resumes rarely word the same pointer identically: compare free-text claims by
    # their words too, so "Built order batching in Go at Zepto" doesn't come back twice.
    wording: dict[str, list[set[str]]] = {}
    for f in existing:
        if f.kind in _FREE_TEXT_KINDS:
            wording.setdefault(f.kind, []).append(_words(f.text))

    created: list[ProfileFact] = []
    skipped = 0
    for candidate in candidates:
        key = dedupe_key(candidate.kind, candidate.text, candidate.structured)
        words = _words(candidate.text)
        near = candidate.kind in _FREE_TEXT_KINDS and any(
            _similar(words, other) for other in wording.get(candidate.kind, []))
        if key in seen or near:  # already approved, already rejected, or repeated
            skipped += 1
            continue
        seen.add(key)
        if candidate.kind in _FREE_TEXT_KINDS:
            wording.setdefault(candidate.kind, []).append(words)
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


# Kinds worth telling the user about when a newer resume leaves them out.
_CAREER_KINDS = ("experience", "achievement", "project", "education", "certification", "skill")


def only_in_older(db: Session, account_id: int, candidates: list[FactCandidate]) -> list[ProfileFact]:
    """Approved career facts this resume does not mention. They stay in the profile: an
    older or differently targeted resume is still true, it just says less."""
    mentioned = {dedupe_key(c.kind, c.text, c.structured) for c in candidates}
    idents = {identity_key(c.kind, c.structured) for c in candidates} - {None}
    return [
        f for f in facts_for(db, account_id, statuses=("approved",))
        if f.kind in _CAREER_KINDS and f.source != "user_confirmed"
        and dedupe_key(f.kind, f.text, f.structured or {}) not in mentioned
        and identity_key(f.kind, f.structured or {}) not in idents
    ]


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


# Kinds the profile holds one of; a new approved one retires the old.
SINGLE_KINDS = ("name", "contact_email", "contact_phone", "location")


def _clean_structured(kind: str, structured: dict[str, Any]) -> dict[str, str]:
    from .extraction import MAX_FIELD_TEXT, STRUCTURED_FIELDS

    out: dict[str, str] = {}
    for name in STRUCTURED_FIELDS:
        value = structured.get(name)
        if isinstance(value, str) and value.strip():
            out[name] = value.strip()[:MAX_FIELD_TEXT]
    return out


def add_user_fact(db: Session, account_id: int, kind: str, text: str, structured: dict[str, Any]) -> ProfileFact:
    """A fact the user typed in: approved, sourced to them, never inferred."""
    if kind in SINGLE_KINDS:
        for old in facts_for(db, account_id, statuses=("approved",)):
            if old.kind == kind:
                old.status = "rejected"
                old.confirmed_at = None
    fact = ProfileFact(
        account_id=account_id, kind=kind, text=text.strip(), structured=_clean_structured(kind, structured),
        source="user_confirmed", inferred=False, status="approved", confirmed_at=_utcnow(),
    )
    db.add(fact)
    db.flush()
    refresh_profile(db, account_id)
    return fact


def update_fact(db: Session, account_id: int, fact_id: str, text: Optional[str],
                structured: Optional[dict[str, Any]]) -> ProfileFact:
    """Correct a fact's wording or fields. A rejected fact is gone as far as the user knows."""
    fact = db.query(ProfileFact).filter(ProfileFact.account_id == account_id, ProfileFact.id == fact_id).first()
    if fact is None or fact.status == "rejected":
        raise FactsNotFound()
    if text is not None:
        fact.text = text.strip()
    if structured is not None:
        fact.structured = {**(fact.structured or {}), **_clean_structured(fact.kind, structured)}
        for name, value in structured.items():  # an explicit null or "" clears the field
            if not (isinstance(value, str) and value.strip()):
                fact.structured.pop(name, None)
        fact.structured = dict(fact.structured)  # new dict: JSON columns track assignment
    fact.inferred = False  # the user has now checked it
    db.flush()
    refresh_profile(db, account_id)
    return fact


# Models phrase single facts as sentences ("Name is Priya.", "Phone: +91 …"). The profile
# shows and forms use the value alone.
_SINGLE_PREFIX = re.compile(
    r"^(?:(?:the\s+)?candidate(?:'s|’s)?\s+)?(?:full\s+)?"
    r"(?:name|phone(?:\s+number)?|mobile(?:\s+number)?|e-?mail(?:\s+address)?|location|city|"
    r"located\s+in|based\s+(?:in|out\s+of)|lives\s+in)\s*(?:is\s+|:\s*|-\s*)?",
    re.I,
)


def single_value(text: str) -> str:
    value = _SINGLE_PREFIX.sub("", (text or "").strip()).strip()
    return value.rstrip(".").strip() or (text or "").strip()


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
    project_by_name: dict[str, dict[str, Any]] = {}
    achievements: list[ProfileFact] = []
    for fact in facts:
        s = fact.structured or {}
        if fact.kind in single:
            identity[single[fact.kind]] = {"value": single_value(fact.text), "fact_id": fact.id}
        elif fact.kind == "link":
            identity["links"].append(_entry(fact, names=("url", "network", "label")))
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
            entry = {**_entry(fact, names=("name", "url")), "bullets": []}
            data["projects"].append(entry)
            if _field(fact, "name"):
                project_by_name.setdefault(_field(fact, "name"), entry)
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
        if role is None and _field(fact, "name"):  # a bullet under a project
            name = _field(fact, "name")
            role = project_by_name.get(name) or next(
                (p for key, p in project_by_name.items() if key and (key in name or name in key)), None)
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


def get_preferences(db: Session, account_id: int) -> dict[str, Any]:
    row = get_profile_row(db, account_id)
    return dict((row.data or {}).get("preferences") or {}) if row else {}


def set_preferences(db: Session, account_id: int, preferences: dict[str, Any]) -> dict[str, Any]:
    """Store job preferences on the candidate profile; refresh_profile keeps them."""
    row = get_profile_row(db, account_id)
    if row is None:
        row = CandidateProfile(account_id=account_id, data={})
        db.add(row)
    row.data = {**(row.data or {}), "preferences": preferences}  # new dict: JSON columns track assignment
    row.updated_at = _utcnow()
    db.flush()
    return preferences


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
    for model in (ProfileVersion, ProfileFact, ResumeUpload, AnswerBankEntry, CandidateProfile):
        db.query(model).filter(model.account_id == account_id).delete(synchronize_session=False)
    db.flush()
