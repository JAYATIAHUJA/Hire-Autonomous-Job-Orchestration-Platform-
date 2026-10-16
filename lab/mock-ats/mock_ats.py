"""Greenhouse-shaped mock employer board. Nothing here talks to a real employer."""

from datetime import datetime, timezone
from html import escape

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

app = FastAPI(title="Hire Mock ATS")

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
def submissions():
    return {"submissions": SUBMISSIONS}
