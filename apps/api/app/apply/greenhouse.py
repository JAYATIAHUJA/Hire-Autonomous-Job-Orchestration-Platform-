"""Plan a Greenhouse application: which value goes into which form field.

The plan is built only from the applicant's own profile. A required question the
profile doesn't answer is never guessed: it goes on a question sheet for the person
to answer (PLAN.md §5.3 standing rule, ADR-005 review-each). The browser part that
fills and submits the form lives in scripts/apply/apply.py.

Form schema comes from the public board API:
    GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}?questions=true
The local mock ATS (lab/mock-ats) serves the same shape under /v1.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1"
GREENHOUSE_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io", "job-boards.eu.greenhouse.io"}
# The mock ATS is reachable as 127.0.0.1:8180 from the host and as mock-ats:8000
# from inside compose (the worker), so both spellings are accepted.
LOCAL_HOSTS = {"127.0.0.1", "localhost", "mock-ats"}

# Decision 6 (ADR-008): disclosure on by default, the user may turn it off.
DISCLOSURE = "Submitted with the help of Hire. The candidate reviewed this application."


@dataclass(frozen=True)
class JobRef:
    board: str
    job_id: int
    api_base: str  # where ?questions=true is read
    form_url: str  # the hosted application page
    is_mock: bool

    @property
    def questions_url(self) -> str:
        return f"{self.api_base}/boards/{self.board}/jobs/{self.job_id}?questions=true"


def parse_job_url(url: str, job_id: Optional[str] = None) -> JobRef:
    """Accept the job links people actually paste.

    boards.greenhouse.io/{board}/jobs/{id}, job-boards.greenhouse.io/{board}/jobs/{id}
    (and its EU twin), .../embed/job_app?for={board}&token={id}, and the local mock ATS
    http://127.0.0.1:8180/boards/{board}/jobs/{id}.

    Many employers wrap the form in their own careers domain
    (www.payoneer.com/careers/job/?gh_jid=…) - the host says nothing, but ingestion
    recorded which board the job came from, so ``job_id`` ("greenhouse_{board}_{id}")
    resolves it when the URL alone can't.
    """
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")

    if host in LOCAL_HOSTS:
        m = re.search(r"/boards/([^/]+)/jobs/(\d+)$", path)
        if not m:
            raise ValueError(f"not a mock ATS job link: {url}")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        board, job_num = m.group(1), int(m.group(2))
        return JobRef(board, job_num, f"{origin}/v1", f"{origin}/boards/{board}/jobs/{job_num}", True)

    if host in GREENHOUSE_HOSTS:
        if path.endswith("/embed/job_app"):
            qs = parse_qs(parsed.query)
            board, token = (qs.get("for") or [""])[0], (qs.get("token") or [""])[0]
            if not board or not token.isdigit():
                raise ValueError(f"embed link without for=/token=: {url}")
            board, job_num = board.lower(), int(token)
        else:
            m = re.search(r"^/([^/]+)/jobs/(\d+)$", path)
            if not m:
                raise ValueError(f"not a Greenhouse job link: {url}")
            board, job_num = m.group(1).lower(), int(m.group(2))
        return JobRef(board, job_num, GREENHOUSE_API, f"https://job-boards.greenhouse.io/{board}/jobs/{job_num}", False)

    # A careers-domain wrapper: the board is in our own job id.
    if job_id:
        m = re.fullmatch(r"greenhouse_([a-z0-9_-]+)_(\d+)", job_id.lower())
        if m:
            board, job_num = m.group(1), int(m.group(2))
            return JobRef(board, job_num, GREENHOUSE_API,
                          f"https://job-boards.greenhouse.io/{board}/jobs/{job_num}", False)

    raise ValueError(f"only Greenhouse job links are supported for now, got {host or url!r}")


# --- the applicant ------------------------------------------------------------


@dataclass
class Applicant:
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    resume_path: str = ""
    cover_letter_path: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    city: str = ""
    # Answers to anything else, keyed by the question's label (case and punctuation ignored).
    answers: dict[str, Any] = field(default_factory=dict)
    # Answers to common questions however a form words them: regex on the label -> value
    # (notice period, CTC, relocation...). Checked after ``answers``.
    topic_answers: dict[str, Any] = field(default_factory=dict)
    # Answers the user gave on earlier forms, keyed by the normalised question. Only
    # reused for the same question in other words - never for free-text or, unless the
    # wording is identical, sensitive ones (see ``remembered_match``).
    remembered: dict[str, str] = field(default_factory=dict)
    disclosure: bool = True

    @classmethod
    def load(cls, path: Path) -> "Applicant":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def problems(self) -> list[str]:
        """What must be fixed before any form is filled."""
        out = []
        for name in ("first_name", "last_name", "email"):
            if not str(getattr(self, name) or "").strip():
                out.append(f"profile is missing {name}")
        if self.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.email):
            out.append("profile email doesn't look like an email address")
        for name in ("resume_path", "cover_letter_path"):
            value = getattr(self, name)
            if value and not Path(value).is_file():
                out.append(f"{name} not found: {value}")
        return out


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# Free-text a candidate writes per job ("why us", essays): remembered answers never fill these.
_FREE_TEXT_QUESTION = re.compile(
    r"\b(why|describe|tell|explain|motivat|cover|essay|anything else|additional)\b", re.IGNORECASE
)
# Legal, pay and EEO questions: only an exactly-identical remembered question may answer.
_SENSITIVE_QUESTION = re.compile(
    r"\b(gender|race|ethnic|veteran|disab|diversit|eeo|authori[sz]|sponsor|visa|salary|compensation|ctc|pay)\b",
    re.IGNORECASE,
)


def remembered_match(remembered: dict[str, str], label: str) -> Optional[tuple[str, str]]:
    """The (normalised question, answer) this form's label can reuse, if any.

    A match needs most of the remembered question's words in the new label, so the
    same question asked in other words counts while a different one does not.
    """
    if not remembered:
        return None
    if _FREE_TEXT_QUESTION.search(label):
        return None
    key = _norm(label)
    if key in remembered:
        return key, remembered[key]
    if _SENSITIVE_QUESTION.search(label):
        return None  # near-miss wording is not good enough here
    label_tokens = set(key.split())
    if len(label_tokens) < 2:
        return None
    for norm, value in remembered.items():
        tokens = set(norm.split())
        if len(tokens) >= 2 and len(tokens & label_tokens) / len(tokens) >= 0.8:
            return norm, value
    return None


# Common questions answered straight from profile fields. Matched on the label.
# Checked after the topics, so "preferred location" beats the plain city fact.
_LABEL_TO_PROFILE = [
    (re.compile(r"\blinked ?in\b"), "linkedin"),
    (re.compile(r"\bgit ?hub\b"), "github"),
    (re.compile(r"\b(website|portfolio|personal site)\b"), "website"),
    (re.compile(r"\b(location|city)\b"), "city"),
]
_STANDARD_FIELDS = {
    "first_name": "first_name",
    "last_name": "last_name",
    "email": "email",
    "phone": "phone",
    "resume": "resume_path",
    "cover_letter": "cover_letter_path",
}


# --- planning -----------------------------------------------------------------


@dataclass
class PlannedAnswer:
    label: str
    field_name: str
    field_type: str
    value: Any  # text, a file path, an option value, or a list of option values
    shown: str  # what the person reviews: the text, file name or option label(s)
    required: bool
    source: str  # profile field or "answers"


@dataclass
class Plan:
    job: JobRef
    title: str
    location: str
    company: str
    answers: list[PlannedAnswer]
    missing: list[dict[str, Any]]  # required questions with no answer: label, field, options
    skipped_optional: list[str]
    unsupported: list[str]  # required fields of a type we can't fill yet
    disclosure_field: Optional[str]

    @property
    def ready(self) -> bool:
        return not self.missing and not self.unsupported

    def to_json(self) -> str:
        data = asdict(self)
        data["job"] = asdict(self.job)
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _option_for(field_def: dict[str, Any], wanted: Any) -> Optional[dict[str, Any]]:
    """The select option a profile answer means: match on label, then on value."""
    options = field_def.get("values") or []
    target = _norm(str(wanted))
    if target in {"true", "y"}:
        target = "yes"
    if target in {"false", "n"}:
        target = "no"
    for opt in options:
        if _norm(str(opt.get("label"))) == target:
            return opt
    for opt in options:
        if _norm(str(opt.get("value"))) == target:
            return opt
    # "Yes" should pick "Yes, I am authorized..." when that is the only yes.
    starts = [o for o in options if _norm(str(o.get("label"))).startswith(target + " ")]
    return starts[0] if len(starts) == 1 else None


def _profile_value(applicant: Applicant, label: str, field_name: str) -> tuple[Any, str]:
    if field_name in _STANDARD_FIELDS:
        attr = _STANDARD_FIELDS[field_name]
        return getattr(applicant, attr), attr
    answers = {_norm(k): v for k, v in applicant.answers.items()}
    key = _norm(label)
    if key in answers:
        return answers[key], "answers"
    if field_name in applicant.answers:
        return applicant.answers[field_name], "answers"
    for pattern, value in applicant.topic_answers.items():
        if re.search(pattern, key):
            return value, "answer bank"
    remembered = remembered_match(applicant.remembered, label)
    if remembered is not None:
        return remembered[1], "remembered"
    for pattern, attr in _LABEL_TO_PROFILE:
        if pattern.search(key):
            return getattr(applicant, attr), attr
    return None, ""


def plan_application(job: JobRef, schema: dict[str, Any], applicant: Applicant) -> Plan:
    """Decide every field's value from the profile; list what's missing. Never guesses."""
    answers: list[PlannedAnswer] = []
    missing: list[dict[str, Any]] = []
    skipped: list[str] = []
    unsupported: list[str] = []
    disclosure_field: Optional[str] = None

    questions = list(schema.get("questions") or []) + list(schema.get("location_questions") or [])
    for q in questions:
        label = (q.get("label") or "").strip()
        required = bool(q.get("required"))
        # Greenhouse geo questions (latitude/longitude) carry only hidden fields: the
        # page fills them itself, a person never types them, so neither do we.
        fields = [f for f in (q.get("fields") or []) if f.get("type") != "input_hidden"]
        if not fields:
            continue
        # Greenhouse offers "attach a file" or "type it" for resume and cover letter;
        # we answer the first kind the profile can fill.
        filled = False
        for f in fields:
            name, ftype = f.get("name") or "", f.get("type") or ""
            value, source = _profile_value(applicant, label, name)
            if value in (None, "", []):
                continue
            if ftype == "input_file":
                answers.append(PlannedAnswer(label, name, ftype, str(value), Path(str(value)).name, required, source))
            elif ftype in ("input_text", "textarea"):
                answers.append(PlannedAnswer(label, name, ftype, str(value), str(value), required, source))
            elif ftype == "multi_value_single_select":
                opt = _option_for(f, value)
                if opt is None:
                    continue  # the profile's answer isn't one of the options: ask
                answers.append(PlannedAnswer(label, name, ftype, opt["value"], str(opt["label"]), required, source))
            elif ftype == "multi_value_multi_select":
                wanted = value if isinstance(value, list) else [value]
                opts = [_option_for(f, w) for w in wanted]
                if not opts or any(o is None for o in opts):
                    continue
                answers.append(PlannedAnswer(
                    label, name, ftype, [o["value"] for o in opts], ", ".join(str(o["label"]) for o in opts), required, source
                ))
            else:
                if required:
                    unsupported.append(f"{label} ({ftype})")
                continue
            filled = True
            break

        if filled:
            continue
        text_field = next((f for f in fields if f.get("type") == "textarea"), None)
        if (
            not required
            and applicant.disclosure
            and disclosure_field is None
            and text_field
            and re.search(r"additional|anything else", label, re.IGNORECASE)
        ):
            answers.append(PlannedAnswer(label, text_field["name"], "textarea", DISCLOSURE, DISCLOSURE, False, "disclosure"))
            disclosure_field = text_field["name"]
            continue
        if required:
            first = fields[0] if fields else {}
            missing.append({
                "label": label,
                "field": first.get("name"),
                "type": first.get("type"),
                "options": [o.get("label") for o in first.get("values") or []],
            })
        else:
            skipped.append(label)

    return Plan(
        job=job,
        title=schema.get("title") or "",
        location=((schema.get("location") or {}).get("name") or ""),
        company=schema.get("company_name") or job.board,
        answers=answers,
        missing=missing,
        skipped_optional=skipped,
        unsupported=unsupported,
        disclosure_field=disclosure_field,
    )


def question_sheet(plan: Plan) -> dict[str, Any]:
    """The missing questions as a fill-in block for the profile's "answers"."""
    return {
        m["label"]: (f"<one of: {' | '.join(m['options'])}>" if m["options"] else "")
        for m in plan.missing
    }


def render_plan(plan: Plan) -> str:
    lines = [
        f"{plan.company} - {plan.title} ({plan.location})",
        f"Form: {plan.job.form_url}" + ("   [MOCK ATS]" if plan.job.is_mock else "   [REAL EMPLOYER]"),
        "",
        "Will fill:",
    ]
    width = max((len(a.label) for a in plan.answers), default=10)
    for a in plan.answers:
        star = "*" if a.required else " "
        lines.append(f"  {star} {a.label.ljust(width)}  {a.shown}")
    if plan.skipped_optional:
        lines.append("")
        lines.append("Left blank (optional): " + "; ".join(plan.skipped_optional))
    if plan.missing:
        lines.append("")
        lines.append("NEEDS YOUR ANSWER (required):")
        for m in plan.missing:
            opts = f"  options: {', '.join(m['options'])}" if m["options"] else ""
            lines.append(f"  - {m['label']}{opts}")
    if plan.unsupported:
        lines.append("")
        lines.append("Can't fill yet (required): " + "; ".join(plan.unsupported))
    if plan.disclosure_field is None:
        lines.append("")
        lines.append("Note: this form has no free-text field for the Hire disclosure line.")
    return "\n".join(lines)
