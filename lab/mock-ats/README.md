# Mock ATS

A tiny stand-in for employer job boards. It lets the apply engine be built and tested
without touching real employers (PLAN.md §12.2).

## Greenhouse-shaped stub board

- `GET /v1/boards/{board}/jobs` lists jobs (a trimmed copy of the Greenhouse Job Board API shape).
- `GET /v1/boards/{board}/jobs/{id}?questions=true` returns one job with its form questions.
- `GET /boards/{board}/jobs/{id}` serves a hosted HTML application form.
- `POST /boards/{board}/jobs/{id}/apply` records a submission, and `GET /_submissions` lists them.

The only board is `acme`. In the dev stack it runs at http://localhost:8180/boards/acme/jobs/4001.

## Form lab: 20 real public forms (`lab/fixtures`)

Saved, sanitised copies of live Greenhouse, Lever and Ashby application forms. See
[`lab/fixtures/INDEX.md`](../fixtures/INDEX.md) for the list and what each one stresses.

- `GET /fixtures` lists the fixtures with their meta.
- `GET /fixtures/{ats}/{id}/` serves the page (`page.html`); assets, `frame.html`, `meta.json`
  and `questions.json` are served next to it. Responses carry a CSP that blocks scripts,
  other hosts and form posts anywhere but this mock.
- `POST /submit` is where every captured form posts. It records the text fields and, for each
  upload, the field name, file name, size and sha256.
- `GET /_submissions?fixture=greenhouse/twilio-7781659` filters the records; `DELETE /_submissions` clears them.

Fixtures are read from `../fixtures` (override with `LAB_FIXTURES_DIR`).

```
cd lab/mock-ats
python -m pytest -q          # hermetic; the Chromium render test skips if Playwright is missing
uvicorn mock_ats:app --port 8180   # then open http://localhost:8180/fixtures
```

Recapturing (needs network; read-only, never submits): see the docstring in
`lab/capture/capture.py`. `pip install -r lab/capture/requirements.txt`,
`python -m playwright install chromium`, then `python lab/capture/capture.py lab/capture/targets.json`
and `python lab/capture/build_index.py`. Postings close, so expect to replace a few targets each time.

Later phases add Workday and chaos scenarios (slow loads, CAPTCHA, OTP, layout drift).
