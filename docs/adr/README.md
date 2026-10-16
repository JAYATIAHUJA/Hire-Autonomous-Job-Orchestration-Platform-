# Architecture decision records

Each ADR records one decision: its context, the choice, and what it costs. Supersede an ADR
with a new one; don't rewrite history.

| # | Decision | Status |
|---|---|---|
| [001](001-automate-only-employer-ats.md) | Automate only employer-owned ATS forms; never LinkedIn or Naukri | Accepted |
| [002](002-preflight-before-swipe.md) | Pre-flight the application form before the card is shown | Accepted |
| [003](003-deterministic-adapters-first.md) | Deterministic adapters first, LLM browser agent as fallback | Accepted |
| [004](004-payload-bound-consent-receipts.md) | Consent receipts bind the exact payload; Ed25519 + hash chain | Accepted |
| [005](005-review-each-default.md) | "Review each" is the default; Autopilot is earned | Accepted |
| [006](006-no-captcha-solvers-no-stealth.md) | No CAPTCHA solvers, no stealth or fingerprint spoofing | Accepted |
| [007](007-one-durable-run-engine.md) | One durable Run engine; never auto-replay a crashed run | Accepted |
| [008](008-launch-decisions.md) | Launch decisions: models, market, disclosure, pricing, licence, runtime | Accepted |
| [009](009-dev-stack-object-store.md) | Dev object store: SeaweedFS instead of MinIO | Accepted |
| [010](010-auth-sessions.md) | Accounts, opaque cookie sessions, CSRF header, owner scoping | Accepted |
