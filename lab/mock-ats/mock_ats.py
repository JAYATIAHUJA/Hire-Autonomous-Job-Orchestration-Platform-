"""Greenhouse-shaped mock employer board. Nothing here talks to a real employer."""

import hashlib
import json
import os
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

app = FastAPI(title="Hire Mock ATS")

FIXTURES_DIR = Path(os.environ.get("LAB_FIXTURES_DIR") or Path(__file__).resolve().parent.parent / "fixtures")
FIXTURE_CSP = (
    "default-src 'self' data:; script-src 'none'; style-src 'self' 'unsafe-inline' data:; "
    "img-src 'self' data:; font-src 'self' data:; frame-src 'self'; form-action 'self'; base-uri 'none'"
)
FIXTURE_SUMMARY_KEYS =("ats", "company", "title", "location", "variant", "field_count", "notable_fields")

QUESTIONS = [
    {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text"}]},
    {"label": "Last Name", "required": True, "fields": [{"name": "last_name", "type": "input_text"}]},
    {"label": "Email", "required": True, "fields": [{"name": "email", "type": "input_text"}]},
    {"label": "Phone", "required": False, "fields": [{"name": "phone", "type": "input_text"}]},
    {"label": "Resume/CV", "required": True, "fields": [{"name": "resume", "type": "input_file"}]},
    {"label": "LinkedIn Profile", "required": False, "fields": [{"name": "question_1001", "type": "input_text"}]},
    {
        "label": "Are you legally authorized to work in India?",
        "required": True,
        "fields": [
            {
                "name": "question_1002",
                "type": "multi_value_single_select",
                "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}],
            }
        ],
    },
    {"label": "Notice period (days)", "required": True, "fields": [{"name": "question_1003", "type": "input_text"}]},
]

JOBS = {
    "acme": [
        {
            "id": 4001,
            "title": "Backend Engineer (Python)",
            "location": {"name": "Bengaluru, India"},
            "content": "Build Python and PostgreSQL services for payments.",
            "updated_at": "2026-10-10T09:00:00Z",
        },
        {
            "id": 4002,
            "title": "Frontend Engineer (React)",
            "location": {"name": "Remote - India"},
            "content": "Own the React web app and design system.",
            "updated_at": "2026-10-12T09:00:00Z",
        },
    ]
}

SUBMISSIONS: list[dict] = []


def _job(board: str, job_id: int) -> dict:
    for job in JOBS.get(board, []):
        if job["id"] == job_id:
            return job
    raise HTTPException(status_code=404, detail="Job not found")


def _with_url(request: Request, board: str, job: dict) -> dict:
    return {**job, "absolute_url": str(request.url_for("hosted_form", board=board, job_id=job["id"]))}


def _control(field: dict, required: bool) -> str:
    name = field["name"]
    req = " required" if required else ""
    if field["type"] == "input_file":
        return f'<input type="file" id="{name}" name="{name}"{req}>'
    if field["type"] == "multi_value_single_select":
        options = "".join(f'<option value="{v["value"]}">{escape(v["label"])}</option>' for v in field["values"])
        return f'<select id="{name}" name="{name}"{req}><option value="">Select...</option>{options}</select>'
    return f'<input type="text" id="{name}" name="{name}"{req}>'


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/boards/{board}/jobs")
def list_jobs(board: str, request: Request):
    if board not in JOBS:
        raise HTTPException(status_code=404, detail="Board not found")
    return {"jobs": [_with_url(request, board, j) for j in JOBS[board]], "meta": {"total": len(JOBS[board])}}


@app.get("/v1/boards/{board}/jobs/{job_id}")
def get_job(board: str, job_id: int, request: Request, questions: bool = False):
    job = _with_url(request, board, _job(board, job_id))
    return {**job, "questions": QUESTIONS} if questions else job


@app.get("/boards/{board}/jobs/{job_id}", response_class=HTMLResponse, name="hosted_form")
def hosted_form(board: str, job_id: int):
    job = _job(board, job_id)
    rows = []
    for q in QUESTIONS:
        field = q["fields"][0]
        label = escape(q["label"]) + (" *" if q["required"] else "")
        rows.append(f'<div class="field"><label for="{field["name"]}">{label}</label>{_control(field, q["required"])}</div>')
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{escape(job['title'])}</title></head><body>"
        f"<h1>{escape(job['title'])}</h1><p>{escape(job['location']['name'])}</p>"
        f'<form id="application_form" method="post" enctype="multipart/form-data" '
        f'action="/boards/{board}/jobs/{job_id}/apply">'
        + "".join(rows)
        + '<button type="submit" id="submit_app">Submit Application</button></form></body></html>'
    )


@app.post("/boards/{board}/jobs/{job_id}/apply", response_class=HTMLResponse)
async def apply(board: str, job_id: int, request: Request):
    _job(board, job_id)
    form = await request.form()
    fields = {key: (getattr(value, "filename", None) or str(value)) for key, value in form.multi_items()}
    missing = [q["fields"][0]["name"] for q in QUESTIONS if q["required"] and not fields.get(q["fields"][0]["name"])]
    if missing:
        raise HTTPException(status_code=422, detail={"missing": missing})
    SUBMISSIONS.append(
        {"board": board, "job_id": job_id, "fields": fields, "received_at": datetime.now(timezone.utc).isoformat()}
    )
    return '<!doctype html><html><body><h1 id="application_confirmation">Thank you for applying.</h1></body></html>'


@app.get("/_submissions")
def submissions(fixture: str | None = None):
    rows = [s for s in SUBMISSIONS if fixture is None or s.get("fixture") == fixture]
    return {"submissions": rows}


@app.delete("/_submissions")
def clear_submissions():
    SUBMISSIONS.clear()
    return {"cleared": True}


# --- Form lab: saved copies of real public application forms (lab/fixtures) ---------------


def fixture_dirs() -> dict[str, Path]:
    """{"<ats>/<id>": dir} for every captured fixture that has a page.html."""
    if not FIXTURES_DIR.is_dir():
        return {}
    return {
        f"{d.parent.name}/{d.name}": d
        for d in sorted(FIXTURES_DIR.glob("*/*"))
        if d.is_dir() and (d / "page.html").is_file()
    }


def _fixture_dir(ats: str, fixture_id: str) -> Path:
    found = fixture_dirs().get(f"{ats}/{fixture_id}")
    if found is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return found


@app.get("/fixtures")
def list_fixtures():
    out = []
    for key, d in fixture_dirs().items():
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").is_file() else {}
        out.append({"fixture": key, "url": f"/fixtures/{key}/", **{k: meta.get(k) for k in FIXTURE_SUMMARY_KEYS}})
    return {"fixtures": out}


@app.get("/fixtures/{ats}/{fixture_id}", include_in_schema=False)
def fixture_redirect(ats: str, fixture_id: str):
    _fixture_dir(ats, fixture_id)
    # the trailing slash matters: pages reference assets/ and frame.html relative to it
    return RedirectResponse(f"/fixtures/{ats}/{fixture_id}/", status_code=307)


@app.get("/fixtures/{ats}/{fixture_id}/{path:path}")
def fixture_file(ats: str, fixture_id: str, path: str = ""):
    root = _fixture_dir(ats, fixture_id).resolve()
    target = (root / (path or "page.html")).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    # Belt and braces: even if a capture missed something, the browser may not run scripts,
    # load anything from another host, or post a form anywhere but this mock.
    return FileResponse(target, headers={"Content-Security-Policy": FIXTURE_CSP})


@app.post("/submit", response_class=HTMLResponse)
async def submit_fixture(request: Request):
    """Every captured form posts here. Records exactly what was sent: text fields, and for
    each upload its field name, file name, size and sha256, so adapter tests can assert on it."""
    form = await request.form()
    fields: dict[str, str | list[str]] = {}
    files: list[dict] = []
    for key, value in form.multi_items():
        if isinstance(value, StarletteUploadFile):
            data = await value.read()
            if not value.filename and not data:
                continue  # an empty file input still posts a part; it carries nothing
            files.append(
                {"field": key, "filename": value.filename, "size": len(data),
                 "sha256": hashlib.sha256(data).hexdigest(), "content_type": value.content_type}
            )
            continue
        if key in fields:
            prev = fields[key]
            fields[key] = [*prev, str(value)] if isinstance(prev, list) else [prev, str(value)]
        else:
            fields[key] = str(value)
    fixture = fields.pop("_lab_fixture", None)
    if isinstance(fixture, list):
        fixture = fixture[0]
    if fixture is None or fixture not in fixture_dirs():
        raise HTTPException(status_code=422, detail="Unknown or missing _lab_fixture")
    SUBMISSIONS.append(
        {"fixture": fixture, "fields": fields, "files": files, "received_at": datetime.now(timezone.utc).isoformat()}
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>Application received</title></head><body>'
        f'<h1 id="application_confirmation">Thank you for applying.</h1><p data-fixture="{escape(fixture)}">'
        "Recorded by the Hire mock ATS. Nothing was sent to the employer.</p></body></html>"
    )
