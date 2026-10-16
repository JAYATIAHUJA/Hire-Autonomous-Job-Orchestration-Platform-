# Mock ATS (stub)

A tiny stand-in for a Greenhouse-style employer job board. It lets the apply engine be
built and tested without touching real employers (PLAN.md §12.2).

Phase 0 ships only the stub:
- `GET /v1/boards/{board}/jobs` lists jobs (a trimmed copy of the Greenhouse Job Board API shape).
- `GET /v1/boards/{board}/jobs/{id}?questions=true` returns one job with its form questions.
- `GET /boards/{board}/jobs/{id}` serves a hosted HTML application form.
- `POST /boards/{board}/jobs/{id}/apply` records a submission, and `GET /_submissions` lists them.

The only board is `acme`. In the dev stack it runs at http://localhost:8180/boards/acme/jobs/4001.

In Phase 4 this grows into the Mock ATS Lab: clones of Greenhouse, Lever, Ashby and Workday
built from saved real form HTML, plus chaos scenarios (slow loads, CAPTCHA, OTP, layout drift).
