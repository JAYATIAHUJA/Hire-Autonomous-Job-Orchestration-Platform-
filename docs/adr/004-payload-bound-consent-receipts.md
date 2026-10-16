# ADR-004: Consent receipts bind the exact payload

- Status: Accepted (2026-10-15)
- Plan: PLAN.md §3.2, §5.10. Fixes B2, B3, B4.

## Context
The original Hire receipt was an HMAC over the employer, job and purpose, signed with a default
secret (B4). It did not cover what was actually sent, its display columns were unsigned (B3),
and a skipped card could be moved to `applied` without one (B2). If an agent submits, the receipt
has to prove that *this exact resume and these exact answers* were approved for *this job on this ATS host*.

## Decision
- **Receipt v2** is canonical JSON that includes `resume_sha256`, `cover_sha256`, `answers_sha256`, `filled_form_sha256` (final submit), `job.ats_host`, `requisition_id`, `mode`, `notice_version` and `prev_hash`.
- There are two receipts in Review mode: **R1 submit intent**, minted on the consent sheet, and **R2 final submit**, minted on the review screen and binding the observed filled-form hash.
- The worker **refuses to click Submit** unless the hash of the payload it is about to send equals the receipt's.
- Receipts are signed with **Ed25519, with the key in KMS**. The public key is published at `/.well-known/hire-receipts.json`. Receipts are hash-chained per user and globally, the daily head is anchored, storage is append-only, and everything returned comes only from the signed payload.
- The stage machine rejects any transition into `submitting` (and, already in Phase 0, onto the board) without a valid receipt.

## Phase 0 status
- Done: B2 (skipped is terminal, and board moves require a verified receipt), B3 (display columns must equal the signed payload), B4 (no default secret; the API refuses to start without a secret of 32+ characters).
- Still HMAC-SHA256 v1. Receipt v2 (Ed25519 + chain + payload hashes) is Phase 3.

## Consequences
- Any edit after approval (a reworded answer, a different resume) needs a new receipt. That is intended.
- Rotating the signing key needs a key-ID field and a published key history.
