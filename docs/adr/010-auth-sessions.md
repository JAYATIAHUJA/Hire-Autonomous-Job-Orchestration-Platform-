# ADR-010: Accounts, opaque cookie sessions and owner scoping

- Status: Accepted (2026-10-16)
- Closes: threat model T13 (unauthenticated API).

## Context
Until Phase 1 the API had no login. `applications.candidate_ref` was free text, so anyone
could read or move anyone's board by typing their handle. `users` is a GitHub profile we
analysed, not a person who logs in. DPDP needs every personal row owned by one person
and erasable.

## Decision
- **Accounts.** `accounts` (id, email unique nullable, display_name, role user|admin|support,
  created_at, deleted_at) is the person. `auth_identities` (provider github|google|email,
  subject, unique together) are the ways in. One account can hold several identities.
- **Logins.** GitHub OAuth (scopes `read:user user:email`; the token is stored Fernet-encrypted
  with `TOKEN_ENCRYPTION_KEY` so the analysis can use the user's rate limit), Google OAuth
  (no token kept), and email OTP (6 digits, 10 minutes, 5 tries, 5 sends/hour per email and
  20 per IP, stored as a sha256 bound to the email). `POST /v1/auth/dev-login` exists only
  when `ENV=dev`.
- **Linking.** A known identity wins. Otherwise a logged-in account adopts the new identity
  (onboarding's "Connect GitHub"). Otherwise an account with the same *verified* email adopts
  it. An unverified provider email never claims an account. A GitHub login claims unowned
  `users` rows with the same username (`users.account_id`).
- **Sessions.** A 32-byte random token in an `HttpOnly; Secure; SameSite=Lax` cookie
  (`hire_session`, 30 days). The database stores only its sha256, so a database leak does
  not leak live sessions. Logout and every new login revoke the old row.
  We chose opaque tokens over JWTs so logout and erasure take effect immediately.
- **CSRF.** SameSite=Lax blocks cross-site POSTs carrying the cookie in modern browsers;
  as a second layer every state-changing request must carry `X-Requested-With`, which a
  cross-site form or a "simple" cross-origin request cannot set. The login endpoints require
  it too (login CSRF). CORS only allows credentials for an explicit origin list.
- **Owner scoping.** Every route except `/health` and `/v1/auth/*` depends on
  `get_current_user`. Applications, consent receipts and the mail ledger carry `account_id`
  and every repository query filters by it. Another account's row is a 404, never a 403.
  `candidate_ref` in requests is ignored; consent receipts are signed for `account:<id>`
  rather than an email, so erasing the email does not touch signed payloads.
- **Legacy data.** Migration 0003 makes one account per distinct old `candidate_ref`
  (with it as the email when it looks like one, so an OTP login claims it) and re-keys the
  mail ledger to `account:<id>|...`.

## Consequences
- The web client must send `credentials: 'include'` and `X-Requested-With` on every call.
- `/jobs/ingest` is admin-only; other job routes need any login.
- The server IMAP mailbox (`IMAP_CANDIDATE_REF`) now names one account by id or email,
  and only that account may trigger a sync from it.
- Not done yet: account erasure endpoint (`DELETE /v1/me`), session listing, OTP rate limits
  behind a proxy (we use the socket peer IP, not `X-Forwarded-For`).
