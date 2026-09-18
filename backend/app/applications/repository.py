"""Persistence for swipes, consent receipts and Kanban stage moves."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from . import models
from .board import BOARD_STAGES, STAGE_APPLIED, STAGE_SKIPPED, can_transition, label_for
from .consent import CONSENT_ALGORITHM, DEFAULT_PURPOSE, issue_consent, verify_payload
from .schemas import ApplicationCard, BoardColumn, BoardResponse, ConsentReceipt, PipelineEventOut


class StageTransitionError(ValueError):
    """Raised when a stage move is not allowed for the requesting actor."""


def _iso(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def new_application_id() -> str:
    return f"app_{uuid.uuid4().hex[:16]}"


def to_consent_receipt(consent: Optional[models.ConsentLog]) -> Optional[ConsentReceipt]:
    if not consent:
        return None
    payload = json.loads(consent.payload_json)
    return ConsentReceipt(
        consent_id=consent.consent_id,
        subject=consent.subject,
        employer_name=consent.employer_name,
        purpose=consent.purpose,
        granted_at=consent.granted_at,
        algorithm=consent.algorithm,
        signature=consent.signature,
        payload=payload,
        verified=verify_payload(payload, consent.signature),
    )


def to_card(app: models.Application) -> ApplicationCard:
    return ApplicationCard(
        application_id=app.application_id,
        job_id=app.job_id,
        candidate_ref=app.candidate_ref,
        employer_name=app.employer_name,
        employer_domain=app.employer_domain,
        role_title=app.role_title,
        location=app.location,
        stage=app.stage,
        stage_label=label_for(app.stage),
        swipe_direction=app.swipe_direction,
        created_at=_iso(app.created_at),
        updated_at=_iso(app.updated_at),
        last_event_summary=app.last_event_summary,
        consent=to_consent_receipt(app.consent),
        events=[
            PipelineEventOut(
                from_stage=e.from_stage,
                to_stage=e.to_stage,
                source=e.source,
                detail=e.detail,
                occurred_at=_iso(e.occurred_at),
            )
            for e in app.events
        ],
    )


def get_application(db: Session, application_id: str) -> Optional[models.Application]:
    return (
        db.query(models.Application)
        .options(joinedload(models.Application.consent), joinedload(models.Application.events))
        .filter(models.Application.application_id == application_id)
        .first()
    )


def find_by_job(db: Session, candidate_ref: str, job_id: str) -> Optional[models.Application]:
    return (
        db.query(models.Application)
        .options(joinedload(models.Application.consent), joinedload(models.Application.events))
        .filter(
            models.Application.candidate_ref == candidate_ref,
            models.Application.job_id == job_id,
        )
        .first()
    )


def swiped_job_ids(db: Session, candidate_ref: str) -> set[str]:
    """Every job the candidate has already ruled on, so the deck never repeats one."""
    rows = db.query(models.Application.job_id).filter(models.Application.candidate_ref == candidate_ref).all()
    return {r[0] for r in rows}


def record_event(
    db: Session,
    app: models.Application,
    *,
    from_stage: Optional[str],
    to_stage: str,
    source: str,
    detail: Optional[str] = None,
    message_uid: Optional[str] = None,
) -> models.PipelineEvent:
    event = models.PipelineEvent(
        application_db_id=app.id,
        from_stage=from_stage,
        to_stage=to_stage,
        source=source,
        detail=detail,
        message_uid=message_uid,
    )
    db.add(event)
    app.last_event_summary = detail
    return event


def record_swipe(
    db: Session,
    *,
    candidate_ref: str,
    job_id: str,
    direction: str,
    employer_name: str,
    employer_domain: Optional[str],
    role_title: str,
    location: Optional[str],
    purpose: Optional[str] = None,
) -> tuple[models.Application, bool]:
    """Apply a swipe. Right consents and enters the board; left skips the card.

    Idempotent per (candidate, job): swiping the same card twice returns the
    existing application instead of issuing a second consent receipt.
    """
    existing = find_by_job(db, candidate_ref, job_id)
    if existing:
        return existing, True

    applied = direction == "right"
    app = models.Application(
        application_id=new_application_id(),
        candidate_ref=candidate_ref,
        job_id=job_id,
        employer_name=employer_name,
        employer_domain=employer_domain,
        role_title=role_title,
        location=location,
        stage=STAGE_APPLIED if applied else STAGE_SKIPPED,
        swipe_direction=direction,
    )
    db.add(app)
    db.flush()

    if applied:
        payload, signature = issue_consent(
            subject=candidate_ref,
            employer_name=employer_name,
            job_id=job_id,
            role_title=role_title,
            purpose=purpose or DEFAULT_PURPOSE,
        )
        db.add(
            models.ConsentLog(
                consent_id=payload["consent_id"],
                application_db_id=app.id,
                subject=payload["subject"],
                employer_name=payload["employer_name"],
                purpose=payload["purpose"],
                granted_at=payload["granted_at"],
                payload_json=json.dumps(payload, sort_keys=True, ensure_ascii=False),
                signature=signature,
                algorithm=CONSENT_ALGORITHM,
            )
        )
        summary = "Consent " + payload["consent_id"] + " signed for " + employer_name + "."
        record_event(db, app, from_stage=None, to_stage=STAGE_APPLIED, source="swipe", detail=summary)
    else:
        record_event(
            db,
            app,
            from_stage=None,
            to_stage=STAGE_SKIPPED,
            source="swipe",
            detail="Card dismissed - no data shared.",
        )

    db.commit()
    db.refresh(app)
    return app, False


def move_stage(
    db: Session,
    app: models.Application,
    to_stage: str,
    *,
    source: str,
    detail: Optional[str] = None,
    message_uid: Optional[str] = None,
) -> models.Application:
    """Move a card, enforcing the transition table for the requesting actor."""
    from_stage = app.stage
    if from_stage == to_stage:
        return app
    if not can_transition(from_stage, to_stage, automated=source == "imap"):
        raise StageTransitionError(
            f"Cannot move {app.application_id} from '{from_stage}' to '{to_stage}' via {source}."
        )

    app.stage = to_stage
    record_event(
        db,
        app,
        from_stage=from_stage,
        to_stage=to_stage,
        source=source,
        detail=detail,
        message_uid=message_uid,
    )
    db.commit()
    db.refresh(app)
    return app


def get_board(db: Session, candidate_ref: str) -> BoardResponse:
    """The candidate's Kanban board, one column per tracked stage."""
    apps = (
        db.query(models.Application)
        .options(joinedload(models.Application.consent), joinedload(models.Application.events))
        .filter(
            models.Application.candidate_ref == candidate_ref,
            models.Application.stage.in_(BOARD_STAGES),
        )
        .order_by(models.Application.updated_at.desc())
        .all()
    )

    by_stage: dict[str, list[ApplicationCard]] = {stage: [] for stage in BOARD_STAGES}
    for app in apps:
        by_stage[app.stage].append(to_card(app))

    return BoardResponse(
        candidate_ref=candidate_ref,
        total=len(apps),
        columns=[
            BoardColumn(stage=stage, label=label_for(stage), count=len(by_stage[stage]), cards=by_stage[stage])
            for stage in BOARD_STAGES
        ],
    )


def open_applications(db: Session) -> list[models.Application]:
    """Cards a recruiter reply could still act on, most recently touched first."""
    return (
        db.query(models.Application)
        .options(joinedload(models.Application.consent), joinedload(models.Application.events))
        .filter(models.Application.stage.in_(BOARD_STAGES))
        .order_by(models.Application.updated_at.desc())
        .all()
    )


def is_message_processed(db: Session, uid: str) -> bool:
    return (
        db.query(models.ProcessedMessage).filter(models.ProcessedMessage.message_uid == uid).first()
        is not None
    )


def mark_message_processed(
    db: Session,
    *,
    uid: str,
    classification: str,
    matched_application_id: Optional[str],
    subject: Optional[str] = None,
    from_address: Optional[str] = None,
) -> None:
    db.merge(
        models.ProcessedMessage(
            message_uid=uid,
            classification=classification,
            matched_application_id=matched_application_id,
            subject=subject,
            from_address=from_address,
        )
    )
    db.commit()
