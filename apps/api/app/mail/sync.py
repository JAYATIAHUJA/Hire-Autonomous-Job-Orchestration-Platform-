"""Matches recruiter replies to cards on the board and moves them.

The hard part is not classification but attribution: a mail says "we", not which
application it answers. Matching is therefore layered, strongest signal first —
the application id quoted in a reply, then the sender's domain against the
employer's, then the employer name in the subject or body.
"""

import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..applications import repository
from ..applications.models import Application
from ..applications.repository import StageTransitionError
from .classifier import ReplyClassification, classify_reply

APPLICATION_ID_RE = re.compile(r"\bapp_[0-9a-f]{8,32}\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")

# Domains that say nothing about which employer sent the mail.
GENERIC_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com",
    "yahoo.co.in", "proton.me", "protonmail.com", "icloud.com", "rediffmail.com",
}

# Two-label public suffixes. Without these, "swiggy.co.in" would reduce to "co.in"
# and match every other Indian company, attaching replies to the wrong card.
MULTI_LABEL_SUFFIXES = {
    "co.in", "co.uk", "co.jp", "co.kr", "co.nz", "co.za", "com.au", "com.br", "com.mx",
    "com.sg", "ac.in", "ac.uk", "edu.in", "gov.in", "net.in", "org.in", "org.uk",
}

# Words that carry no identity once an employer name is split into tokens.
COMPANY_STOPWORDS = {
    "the", "inc", "inc.", "llc", "ltd", "ltd.", "limited", "pvt", "private",
    "technologies", "technology", "tech", "labs", "systems", "solutions",
    "software", "services", "group", "engineering", "india", "global", "co",
}


def sender_domain(from_address: str) -> Optional[str]:
    match = EMAIL_RE.search(from_address or "")
    if not match:
        return None
    domain = match.group(1).lower()
    return None if domain in GENERIC_MAIL_DOMAINS else domain


def _root_domain(domain: Optional[str]) -> Optional[str]:
    """'careers.swiggy.com' and 'swiggy.com' should match each other - but 'a.co.in'
    and 'b.co.in' must not, so two-label public suffixes keep a third label."""
    if not domain:
        return None
    parts = domain.lower().strip(".").split(".")
    if len(parts) < 2:
        return domain.lower()
    if ".".join(parts[-2:]) in MULTI_LABEL_SUFFIXES:
        return ".".join(parts[-3:]) if len(parts) >= 3 else None
    return ".".join(parts[-2:])


def company_tokens(name: str) -> list[str]:
    """Distinctive lowercase tokens of an employer name."""
    raw = re.split(r"[^a-z0-9]+", (name or "").lower())
    return [t for t in raw if len(t) > 2 and t not in COMPANY_STOPWORDS]


def match_application(
    message: dict[str, Any],
    applications: list[Application],
) -> tuple[Optional[Application], str]:
    """Find the card a recruiter reply belongs to, and say how it was matched."""
    if not applications:
        return None, "no open applications"

    haystack = " ".join([message.get("subject") or "", message.get("body") or ""])

    # 1. The reply quotes our application id — unambiguous.
    for quoted in APPLICATION_ID_RE.findall(haystack):
        for app in applications:
            if app.application_id.lower() == quoted.lower():
                return app, "application id in reply"

    # 2. The sender's domain is the employer's domain.
    from_root = _root_domain(sender_domain(message.get("from_address", "")))
    if from_root:
        for app in applications:
            if _root_domain(app.employer_domain) == from_root:
                return app, f"sender domain {from_root}"

    # 3. The employer's name appears in the mail (or in the sender's display name).
    name_haystack = (haystack + " " + (message.get("from_address") or "")).lower()
    best: Optional[Application] = None
    best_hits = 0
    for app in applications:
        tokens = company_tokens(app.employer_name)
        if not tokens:
            continue
        hits = sum(1 for token in tokens if token in name_haystack)
        if hits and hits > best_hits:
            best, best_hits = app, hits
    if best:
        return best, f"employer name in message ({best_hits} token match)"

    return None, "no matching card"


def apply_message(
    db: Session,
    message: dict[str, Any],
    applications: list[Application],
) -> dict[str, Any]:
    """Classify one reply and move its card. Returns what happened, for the report."""
    uid = str(message.get("uid") or "")
    outcome: dict[str, Any] = {
        "uid": uid,
        "subject": message.get("subject", ""),
        "matched": False,
        "moved": False,
    }

    classification: ReplyClassification = classify_reply(
        subject=message.get("subject", ""), body=message.get("body", "")
    )
    outcome["classification"] = classification.stage
    outcome["confidence"] = classification.confidence
    outcome["summary"] = classification.summary

    if not classification.is_decision:
        repository.mark_message_processed(
            db,
            uid=uid,
            classification="none",
            matched_application_id=None,
            subject=message.get("subject"),
            from_address=message.get("from_address"),
        )
        return outcome

    app, how = match_application(message, applications)
    outcome["match_reason"] = how
    if not app:
        repository.mark_message_processed(
            db,
            uid=uid,
            classification=classification.stage,
            matched_application_id=None,
            subject=message.get("subject"),
            from_address=message.get("from_address"),
        )
        return outcome

    outcome["matched"] = True
    outcome["application_id"] = app.application_id
    outcome["employer_name"] = app.employer_name
    outcome["from_stage"] = app.stage

    detail = f"{classification.summary} Matched by {how}."
    try:
        repository.move_stage(db, app, classification.stage, source="imap", detail=detail, message_uid=uid)
        outcome["moved"] = True
        outcome["to_stage"] = classification.stage
    except StageTransitionError as exc:
        outcome["error"] = str(exc)

    repository.mark_message_processed(
        db,
        uid=uid,
        classification=classification.stage,
        matched_application_id=app.application_id,
        subject=message.get("subject"),
        from_address=message.get("from_address"),
    )
    return outcome


def sync_messages(db: Session, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Run a batch of recruiter replies through matching and stage moves."""
    stats: dict[str, Any] = {"fetched": len(messages), "matched": 0, "moved": 0, "skipped": 0, "errors": [], "moves": []}

    for message in messages:
        uid = str(message.get("uid") or "")
        if not uid or repository.is_message_processed(db, uid):
            stats["skipped"] += 1
            continue

        # Re-read the board per message: an earlier mail may have moved a card.
        applications = repository.open_applications(db)
        outcome = apply_message(db, message, applications)

        if outcome.get("matched"):
            stats["matched"] += 1
        if outcome.get("moved"):
            stats["moved"] += 1
            stats["moves"].append(outcome)
        elif outcome.get("error"):
            stats["errors"].append(outcome["error"])
        else:
            stats["skipped"] += 1

    return stats
