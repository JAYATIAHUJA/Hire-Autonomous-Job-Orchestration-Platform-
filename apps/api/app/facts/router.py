"""HTTP endpoints for resume parsing, fact review, the assembled profile and the answer bank.

Nothing extracted from a resume is trusted until the user approves it: uploads only ever
create ``proposed`` facts, and GET /v1/profile is built from ``approved`` facts alone.
"""

import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from ..auth.consents import require_resume_consent
from ..auth.deps import Account, get_current_user
from ..db import get_db
from ..llm.client import LLMClient, LLMError, LLMRefusal, get_llm_client
from . import repository
from .documents import DOCX, MAX_RESUME_BYTES, UnsupportedDocument, extract_text, sniff_content_type
from .extraction import FACT_KINDS, extract_facts
from .models import new_upload_id
from .schemas import (
    AnswerBank,
    AnswerBankResponse,
    FactBatchResponse,
    FactCreate,
    FactIdsRequest,
    FactOut,
    FactUpdate,
    ProfileResponse,
    ResumeUploadResponse,
)
from .storage import ObjectStore, get_object_store, require_store

logger = logging.getLogger("hire.facts")

router = APIRouter(prefix="/v1/profile", tags=["facts"])
# Its own router: WP1 owns GET /v1/me, so the answer bank mounts beside it, not inside it.
answer_bank_router = APIRouter(prefix="/v1/me/answer-bank", tags=["facts"])


@router.post("/resume", response_model=ResumeUploadResponse)
def upload_resume(
    file: UploadFile = File(...),
    batch: bool = Query(default=False, description="One of several resumes uploaded together: keep earlier pending proposals"),
    account: Account = Depends(require_resume_consent),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    store: Optional[ObjectStore] = Depends(get_object_store),
):
    """Parse a PDF/DOCX resume (max 5 MB) into fact proposals for the user to review."""
    data = file.file.read(MAX_RESUME_BYTES + 1)
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume must be 5 MB or smaller.")
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    try:
        content_type = sniff_content_type(data)
    except UnsupportedDocument as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    try:
        extracted = extract_text(data)
    except UnsupportedDocument as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    store = require_store(store)
    sha256 = hashlib.sha256(data).hexdigest()
    upload_id = new_upload_id()
    object_key = f"resumes/{account.id}/{upload_id}{'.docx' if content_type == DOCX else '.pdf'}"
    store.put(object_key, data, content_type)

    try:
        result = extract_facts(llm, account_id=account.id, extracted=extracted, file_bytes=data)
        repository.record_upload(
            db, account_id=account.id, object_key=object_key, sha256=sha256, content_type=content_type,
            size_bytes=len(data), upload_id=upload_id,
            text_source="pdf_document" if extracted.needs_pdf_fallback else "text_layer",
        )
        proposals, skipped = repository.create_proposals(
            db, account_id=account.id, source="resume", source_ref=upload_id, candidates=result.facts,
            keep_pending=batch,
        )
        kept = repository.only_in_older(db, account.id, result.facts)
        db.commit()
    except Exception as exc:
        # Keep nothing we can't use: no orphaned file, no half-written proposals.
        db.rollback()
        store.delete(object_key)
        if isinstance(exc, LLMRefusal):
            raise HTTPException(status_code=422, detail="This document could not be processed.") from exc
        if isinstance(exc, LLMError):
            logger.warning("resume parse failed for account_id=%s: %s", account.id, exc)
            raise HTTPException(status_code=502, detail="Resume parsing failed; try again shortly.") from exc
        raise

    approved = {f.id: f for f in repository.facts_for(db, account.id, statuses=("approved",))}
    return ResumeUploadResponse(
        upload_id=upload_id,
        sha256=sha256,
        text_source="pdf_document" if extracted.needs_pdf_fallback else "text_layer",
        proposals=[repository.to_out(f, approved) for f in proposals],
        skipped_duplicates=skipped,
        contains_instructions=result.contains_instructions,
        kept_from_before=[repository.to_out(f, approved) for f in kept],
    )


def _set_status(payload: FactIdsRequest, status: str, account: Account, db: Session) -> FactBatchResponse:
    try:
        facts = repository.set_status(db, account.id, payload.ids, status)
    except repository.FactsNotFound as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail="One or more facts were not found.") from exc
    db.commit()
    return FactBatchResponse(facts=[repository.to_out(f) for f in facts])


@router.post("/facts/approve", response_model=FactBatchResponse)
def approve_facts(payload: FactIdsRequest, account: Account = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    return _set_status(payload, "approved", account, db)


@router.post("/facts", response_model=FactOut, status_code=201)
def add_fact(payload: FactCreate, account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add something the resume missed: a project, an achievement under a role, a skill."""
    if payload.kind not in FACT_KINDS:
        raise HTTPException(status_code=422, detail=f"Unknown kind {payload.kind!r}.")
    fact = repository.add_user_fact(db, account.id, payload.kind, payload.text, payload.structured)
    db.commit()
    return repository.to_out(fact)


@router.patch("/facts/{fact_id}", response_model=FactOut)
def edit_fact(fact_id: str, payload: FactUpdate, account: Account = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """Fix the wording or fields of a proposed or approved fact (yours only)."""
    try:
        fact = repository.update_fact(db, account.id, fact_id, payload.text, payload.structured)
    except repository.FactsNotFound as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail="Fact not found.") from exc
    db.commit()
    return repository.to_out(fact)


@router.post("/facts/reject", response_model=FactBatchResponse)
def reject_facts(payload: FactIdsRequest, account: Account = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return _set_status(payload, "rejected", account, db)


@router.get("", response_model=ProfileResponse)
def get_profile(account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    """The profile assembled from approved facts, plus proposals still awaiting review."""
    row = repository.refresh_profile(db, account.id)
    db.commit()
    approved = {f.id: f for f in repository.facts_for(db, account.id, statuses=("approved",))}
    pending = repository.facts_for(db, account.id, statuses=("proposed",))
    return ProfileResponse(
        profile=row.data,
        pending_proposals=[repository.to_out(f, approved) for f in pending],
        updated_at=row.updated_at,
    )


@router.delete("", status_code=204)
def delete_profile(
    account: Account = Depends(get_current_user),
    db: Session = Depends(get_db),
    store: Optional[ObjectStore] = Depends(get_object_store),
):
    """DPDP erasure: facts, profile, answer bank and every stored resume file."""
    try:
        repository.erase_account_data(db, account.id, store)
    except Exception as exc:
        db.rollback()
        logger.error("erasure failed for account_id=%s: %s", account.id, exc)
        raise HTTPException(status_code=503, detail="Erasure could not finish; nothing was deleted. Retry.") from exc
    db.commit()
    return Response(status_code=204)


def _answer_bank_response(entries) -> AnswerBankResponse:
    return AnswerBankResponse(
        answers={e.key: e.value for e in entries},
        updated_at=max((e.updated_at for e in entries if e.updated_at), default=None),
    )


@answer_bank_router.get("", response_model=AnswerBankResponse)
def get_answer_bank(account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    return _answer_bank_response(repository.get_answer_bank(db, account.id))


@answer_bank_router.put("", response_model=AnswerBankResponse)
def put_answer_bank(payload: AnswerBank, account: Account = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Replace the whole answer bank (keys left out are removed)."""
    entries = repository.replace_answer_bank(db, account.id, payload.answers)
    db.commit()
    return _answer_bank_response(entries)
