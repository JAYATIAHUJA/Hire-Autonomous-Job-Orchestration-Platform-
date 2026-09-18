# HIRE — Autonomous Job Orchestration Platform

**Objective 1: GitHub proof-of-work profile.** HIRE reads the actual diffs of a developer's commits and merged pull requests and builds a skills profile where every skill is backed by the developer's *own* changes: the files they touched, the libraries they imported and the dependencies they added. Each skill links to concrete commits/PRs and shows a transparent evidence checklist instead of an opaque score. Background and rationale: [`deep-research-report.md`](deep-research-report.md).

**Objective 3: client interface and pipeline tracker.** A mobile-first PWA deals the ghost-filtered listings out as swipeable cards. A swipe right is the affirmative consent action: it writes a signed log naming the employer, the purpose and the moment consent was given, and puts a card on the pipeline board. A background IMAP service then reads recruiter replies and moves that card from **Applied** to **Interview Scheduled** or **Rejected** on its own.

## Architecture

```
frontend (React + Vite + TS)  --/api-->  backend (FastAPI)  -->  GitHub REST API
                                              |
                                              v
                                         SQLite (SQLAlchemy)
```

### How a profile is built (`backend/app`)

| Step | File | What it does |
|---|---|---|
| Fetch | `github_client.py`, `services/fetch_service.py` | Async, bounded concurrency. Non-fork repos → authored commit list, contributor stats, full diffs of recent non-merge commits. Plus merged PRs to *other people's* repos (search + PR files). |
| Files | `analysis/files.py` | Language by extension and category: source, test, docs, ci, infra, manifest, lockfile, generated. Lockfiles and generated/vendored code are ignored. |
| Imports | `analysis/imports.py` | Imports on **added** lines only (JS/TS, Python, notebooks, Go, Java/Kotlin, Rust, Ruby, PHP, C#, Dart) and dependencies added to manifests. |
| Work type | `analysis/commits.py` | feature / fix / refactor / test / ci-infra / docs / chore from conventional-commit prefixes, file mix and keywords. Huge commits are flagged as bulk imports. |
| Contribution | `analysis/contribution.py` | One evidence record per commit/PR with a weight: log-scaled own lines × work type, ×2 for merged external PRs, ×0.1 for bulk. |
| Skills | `analysis/skills.py`, `skill_rules.json` | Languages from files you changed; frameworks/practices from imports, dependencies, paths and categories. Credit covers only the files that show the skill. |
| Role | `analysis/roles.py` | Primary author / lead / core / contributor from your share of repo commits; external contributor for merged PRs elsewhere. |
| Confidence | `analysis/confidence.py` | Checklist: substantial own code (≥500 lines), used across projects, accepted by others (merged external PR), sustained (≥3 months), recent (6 months), built features. **Strong** = ≥4 incl. substantial code · **Moderate** = ≥3 or substantial code · else **Limited**. |
| Proof | `analysis/highlights.py` | Top distinct contributions per skill and for the whole profile. |
| API | `routers/profile.py` | `POST /api/profile/analyze` `{username, token?}` → `{profile_id}` · `GET /api/profile/{id}` |

To teach it a new framework or tool, add an entry to `backend/app/skill_rules.json` (`imports`, `dependencies`, `paths`, `categories`).

### How a swipe becomes a tracked application (Objective 3)

| Step | File | What it does |
|---|---|---|
| Deck | `routers/applications.py` | `GET /api/applications/deck` serves ghost-filtered jobs minus everything this candidate already swiped. |
| Consent | `applications/consent.py` | A swipe right mints a receipt — consent id, subject, **named employer**, job, purpose, UTC timestamp — signed HMAC-SHA256 over a canonical JSON encoding. Re-verified on every read. |
| Board | `applications/board.py` | Stage vocabulary and the transition table. Manual moves and automated (mail-driven) moves have separate rules: the mail reader can close a card, never reopen one. |
| Storage | `applications/models.py`, `repository.py` | `Application` (the card), `ConsentLog` (the receipt), `PipelineEvent` (audit trail of every move), `ProcessedMessage` (so a re-poll never double-moves a card). |
| Reply parsing | `mail/imap_client.py` | Stdlib `imaplib` + `email`: reads the mailbox **read-only**, decodes headers, prefers the text/plain part. Any IMAP inbox and an app password will do. |
| Classification | `mail/classifier.py` | Weighted phrase matching scores rejection and interview language separately, so "Unfortunately that slot is taken" still reads as an interview and "thanks for interviewing, but…" still reads as a rejection. |
| Matching | `mail/sync.py` | Attributes a reply to a card: quoted application id, then sender domain vs employer domain, then employer name in the subject/body. |
| Background service | `mail/poller.py` | Polls the mailbox on an interval alongside the API when `IMAP_ENABLED=true`; blocking IMAP work runs in a worker thread. |
| PWA | `frontend/public/manifest.webmanifest`, `public/sw.js` | Installable, portrait, standalone. App shell is cache-first, `/api` reads are network-first with a cached fallback. |
| UI | `frontend/src/pages/SwipePage.tsx`, `PipelinePage.tsx` | Drag-to-swipe deck (pointer events, ← → keys, buttons) and the three-column board with per-card consent badge and audit trail. |

Endpoints: `GET /api/applications/deck` · `POST /api/applications/swipe` · `GET /api/applications/board` · `GET /api/applications/{id}` · `GET /api/applications/{id}/consent` · `POST /api/applications/{id}/stage` · `POST /api/mail/sync`.

## Running locally

**Backend** (Python 3.11+):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # optional, defaults work
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs · Tests: `pytest`

There are no migrations yet: after pulling schema changes, delete `backend/hire.db` and it is recreated on startup.

**Frontend** (Node 18+):

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to the backend on port 8000.

The swipe deck is at `/swipe` and the pipeline board at `/pipeline`. The service worker only registers in a production build (`npm run build && npm run preview`), so a cached shell never hides your edits during `npm run dev`.

## Recruiter mailbox (Objective 3)

The background reader is off by default. To switch it on, set these in `backend/.env` and restart the API:

```
IMAP_ENABLED=true
IMAP_HOST=imap.gmail.com
IMAP_USER=you@example.com
IMAP_PASSWORD=your-app-password     # an app password, never your login password
IMAP_SEARCH=UNSEEN
IMAP_POLL_SECONDS=300
```

The mailbox is opened read-only, so nothing is ever marked as seen or deleted. Without it, `POST /api/mail/sync` still works: post `{"messages": [...]}` to replay replies through the same classifier and matcher — the **Replay a recruiter reply** panel on the board does exactly that.

`CONSENT_SIGNING_SECRET` signs the consent receipts. Change it in production; rotating it means receipts signed with the old secret no longer verify.

## GitHub access and rate limits

OAuth login is **not built yet**. For now, enter a GitHub username and optionally a personal access token (PAT). The token is used only for that analysis and never stored.

- **Without a token (limited mode):** GitHub allows 60 requests/hour, so 3 repos, 8 commits per repo and 5 external PRs are read (~30–40 requests).
- **With a token (full mode):** 5,000 requests/hour; up to 20 repos, 40 commits per repo and 30 external PRs. If the token belongs to the same user, private repos are included.

Limits are configurable in `.env` (see `.env.example`).

## Roadmap

- GitHub OAuth login (replaces the PAT field)
- Re-analysis / caching per user instead of a new profile each run
- LLM-written contribution summaries and resume bullets that must cite the stored commits/PRs (Objective 2)
- Sending the application itself (the consent receipt is written, the outbound submission is still manual)
- Push notifications when the IMAP reader moves a card while the PWA is closed
