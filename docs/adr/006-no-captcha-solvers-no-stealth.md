# ADR-006: No CAPTCHA solvers, no stealth or fingerprint spoofing

- Status: Accepted (2026-10-15)
- Plan: PLAN.md §5.12, §9.4

## Context
ATS vendors (Greenhouse, Ashby) score traffic for fraud. CAPTCHA-solving services and stealth
browsers would raise success rates for a while, but they are an arms race. They put Hire on the
wrong side of the employer relationship and conflict with the product's honesty principle.

## Decision
- The Apply Computer is a real Chromium with its default user agent. No fingerprint spoofing, no CAPTCHA-solving services, no residential-proxy rotation.
- When a site challenges the bot (CAPTCHA, unusual verification), the run raises a `takeover` human request and the user solves it from their phone through the live view.
- Volume per employer is low, and the user's real email and phone are used. Egress is a stable IP per user.
- For sensitive sites, the Phase 7 Companion extension applies from the user's own browser and IP.

## Consequences
- Some runs need a human touch. That shows in the human-touch-rate metric per tier.
- Hire stays legally and ethically defensible, and is less likely to be blocked wholesale by an ATS vendor.
