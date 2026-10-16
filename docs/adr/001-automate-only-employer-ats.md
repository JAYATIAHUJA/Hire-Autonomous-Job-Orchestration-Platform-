# ADR-001: Automate only employer-owned ATS forms

- Status: Accepted (2026-10-15)
- Plan: PLAN.md §0, §5.13, §9.1

## Context
A swipe-to-apply product needs to submit applications somewhere. The biggest Indian job
platforms (LinkedIn and Naukri) ban automated access in their terms, and LinkedIn actively
litigates against scraping and automation. No ATS offers a third-party "apply on behalf" API.
Employer-owned ATS forms (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, and later
Darwinbox and Keka) are the employer's own public intake, and the candidate is entitled to use them.

## Decision
- Hire automates **only** the employer's own ATS forms, acting as the candidate, at low volume and with the candidate's real identity.
- **LinkedIn, Naukri, Indeed, Instahyre, Wellfound and email-only jobs are Tier C: Assisted Apply.** Hire builds the packet (tailored resume, answers, copy buttons, deep link), and the user applies themselves. "I applied" moves the card. No submission receipt is minted, because Hire did not submit.
- Job *discovery* follows each source's terms: public ATS board APIs, aggregator APIs per their terms, RSS with attribution, and user-pasted URLs. LinkedIn and Naukri are never scraped.

## Consequences
- Lower reach at launch: many Indian roles are only on Naukri or LinkedIn. We mitigate this with an ATS registry of India-hiring companies (the day-1 seed is 300 companies) and the Assisted Apply flow.
- No account-ban or lawsuit risk to users or to Hire from those platforms.
- The source registry has to record which tier each job is, so the deck shows an effort badge.
