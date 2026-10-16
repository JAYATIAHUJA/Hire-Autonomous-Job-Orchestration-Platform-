import hashlib
import json
import re
import socket
import threading
import time
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from mock_ats import FIXTURES_DIR, SUBMISSIONS, app, fixture_dirs

client = TestClient(app)


def test_board_lists_jobs_with_hosted_form_urls():
    jobs = client.get("/v1/boards/acme/jobs").json()["jobs"]
    assert [j["id"] for j in jobs] == [4001, 4002]
    assert jobs[0]["absolute_url"].endswith("/boards/acme/jobs/4001")


def test_questions_and_hosted_form_agree():
    questions = client.get("/v1/boards/acme/jobs/4001?questions=true").json()["questions"]
    html = client.get("/boards/acme/jobs/4001").text
    for q in questions:
        assert f'name="{q["fields"][0]["name"]}"' in html


def test_submit_records_and_rejects_missing_required_fields():
    SUBMISSIONS.clear()
    bad = client.post("/boards/acme/jobs/4001/apply", data={"first_name": "Ana"})
    assert bad.status_code == 422

    ok = client.post(
        "/boards/acme/jobs/4001/apply",
        data={"first_name": "Ana", "last_name": "Rao", "email": "ana@example.com",
              "question_1002": "1", "question_1003": "30"},
        files={"resume": ("resume.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert ok.status_code == 200
    assert "application_confirmation" in ok.text
    assert client.get("/_submissions").json()["submissions"][0]["fields"]["resume"] == "resume.pdf"


# --- Form lab fixtures --------------------------------------------------------------------

FIXTURES = fixture_dirs()
FIXTURE_IDS = sorted(FIXTURES)
EXPECTED_MIX = {"greenhouse": 8, "lever": 6, "ashby": 6}
META_KEYS = {"url", "captured_at", "ats", "field_count", "notable_fields"}
RESUME = b"%PDF-1.4\n% Hire lab test resume\n"
COVER = b"%PDF-1.4\n% Hire lab test cover letter\n"
SKIP_TYPES = {"submit", "button", "reset", "image"}
# Attribute values that would make a browser reach out to another host.
EXTERNAL = re.compile(r"^\s*(https?:)?//", re.I)
URL_ATTRS = {"src", "href", "action", "formaction", "poster", "data", "background", "srcset"}


class FormInventory(HTMLParser):
    """Collects every <form> and its controls, plus anything that could leave the page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self.stack: list[dict] = []
        self.scripts = 0
        self.iframes: list[str] = []
        self.external: list[str] = []
        self.stylesheets: list[str] = []
        self._select: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        for k, v in a.items():
            if k in URL_ATTRS and EXTERNAL.match(v):
                self.external.append(f"<{tag} {k}={v[:80]}>")
        if tag == "script":
            self.scripts += 1
        elif tag == "iframe":
            self.iframes.append(a.get("src", ""))
        elif tag == "link" and "stylesheet" in a.get("rel", ""):
            self.stylesheets.append(a.get("href", ""))
        elif tag == "form":
            form = {"action": a.get("action"), "method": a.get("method", "").lower(),
                    "enctype": a.get("enctype", ""), "controls": []}
            self.forms.append(form)
            self.stack.append(form)
        elif tag in ("input", "select", "textarea") and self.stack:
            ctl = {"tag": tag, "name": a.get("name", ""), "type": a.get("type", "text").lower(),
                   "value": a.get("value", ""), "options": [], "disabled": "disabled" in a}
            self.stack[-1]["controls"].append(ctl)
            if tag == "select":
                self._select = ctl
        elif tag == "option" and self._select is not None:
            self._select["options"].append(a.get("value"))

    def handle_endtag(self, tag):
        if tag == "form" and self.stack:
            self.stack.pop()
        elif tag == "select":
            self._select = None


def inventory(html: str) -> FormInventory:
    inv = FormInventory()
    inv.feed(html)
    inv.close()
    return inv


def form_document(key: str) -> tuple[str, str]:
    """(path, html) of the document holding the application form (the iframe for embeds)."""
    meta = json.loads((FIXTURES[key] / "meta.json").read_text(encoding="utf-8"))
    path = meta.get("frame") or "page.html"
    return path, client.get(f"/fixtures/{key}/{path}").text


def application_form(inv: FormInventory) -> dict:
    with_file = [f for f in inv.forms if any(c["type"] == "file" for c in f["controls"])]
    return max(with_file or inv.forms, key=lambda f: len(f["controls"]))


def scripted_payload(form: dict) -> tuple[dict, list]:
    """Fill every control the way a dumb adapter would: text everywhere, first real option,
    every checkbox ticked, the first radio of each group, a resume in the first file input."""
    data: dict[str, list[str]] = {}
    files = []
    radios_done = set()
    file_n = 0
    for c in form["controls"]:
        name, typ = c["name"], c["type"]
        if not name or c["disabled"] or typ in SKIP_TYPES:
            continue
        if typ == "file":
            body, fname = (RESUME, "resume.pdf") if file_n == 0 else (COVER, f"cover-{file_n}.pdf")
            files.append((name, (fname, body, "application/pdf")))
            file_n += 1
        elif typ == "hidden":
            data.setdefault(name, []).append(c["value"])
        elif c["tag"] == "select":
            real = [o for o in c["options"] if o]
            data.setdefault(name, []).append(real[0] if real else "")
        elif typ == "checkbox":
            data.setdefault(name, []).append(c["value"] or "on")
        elif typ == "radio":
            if name not in radios_done:
                radios_done.add(name)
                data.setdefault(name, []).append(c["value"] or "on")
        elif typ == "email":
            data.setdefault(name, []).append("ana.rao@example.com")
        else:
            data.setdefault(name, []).append("lab-test")
    return data, files


def test_fixture_mix_is_complete():
    by_ats: dict[str, int] = {}
    for key in FIXTURE_IDS:
        by_ats[key.split("/")[0]] = by_ats.get(key.split("/")[0], 0) + 1
    assert by_ats == EXPECTED_MIX, by_ats
    embeds = [k for k in FIXTURE_IDS if json.loads((FIXTURES[k] / "meta.json").read_text(encoding="utf-8")).get("frame")]
    assert len(embeds) == 2


def test_fixture_index_lists_every_fixture():
    listed = {f["fixture"] for f in client.get("/fixtures").json()["fixtures"]}
    assert listed == set(FIXTURE_IDS)
    index = (FIXTURES_DIR / "INDEX.md").read_text(encoding="utf-8")
    for key in FIXTURE_IDS:
        assert key in index


@pytest.mark.parametrize("key", FIXTURE_IDS)
def test_fixture_loads_offline_and_posts_only_to_the_mock(key):
    meta = json.loads((FIXTURES[key] / "meta.json").read_text(encoding="utf-8"))
    assert META_KEYS <= meta.keys()
    assert meta["ats"] == key.split("/")[0]

    page = client.get(f"/fixtures/{key}/")
    assert page.status_code == 200
    assert "script-src 'none'" in page.headers["content-security-policy"]

    path, html = form_document(key)
    inv = inventory(html)
    assert inv.scripts == 0, "captured page still carries scripts"
    assert inv.external == [], inv.external[:5]
    assert inv.forms, "no <form> in fixture"
    for form in inv.forms:
        assert form["action"] == "/submit" and form["method"] == "post"
        assert "multipart/form-data" in form["enctype"]
    form = application_form(inv)
    assert {"name": "_lab_fixture", "value": key} in [{"name": c["name"], "value": c["value"]} for c in form["controls"]]
    assert any(c["type"] == "file" for c in form["controls"]), "application form has no file upload"
    for href in inv.stylesheets:
        assert client.get(f"/fixtures/{key}/{href}").status_code == 200, href
    if meta.get("frame"):
        outer = inventory(page.text)
        assert outer.iframes == [meta["frame"]]
    # job descriptions are cut to an excerpt; the form tests do not need them
    if 'class="job__description' in html:
        assert html.count('class="job__description') == html.count('data-lab-trimmed="1"')
    for content in re.findall(r'<meta[^>]+description"[^>]*content="([^"]*)"', html):
        assert len(content) <= 300


@pytest.mark.parametrize("key", FIXTURE_IDS)
def test_scripted_submit_is_recorded_exactly(key):
    client.delete("/_submissions")
    _, html = form_document(key)
    form = application_form(inventory(html))
    data, files = scripted_payload(form)

    resp = client.post("/submit", data=data, files=files)
    assert resp.status_code == 200
    assert "application_confirmation" in resp.text

    [rec] = client.get("/_submissions", params={"fixture": key}).json()["submissions"]
    assert rec["fixture"] == key
    sent = {k: (v[0] if len(v) == 1 else v) for k, v in data.items() if k != "_lab_fixture"}
    assert rec["fields"] == sent
    assert [(f["field"], f["filename"], f["sha256"]) for f in rec["files"]] == [
        (name, fname, hashlib.sha256(body).hexdigest()) for name, (fname, body, _) in files
    ]


def test_submit_rejects_unknown_fixture():
    assert client.post("/submit", data={"_lab_fixture": "greenhouse/nope"}).status_code == 422
    assert client.post("/submit", data={"first_name": "Ana"}).status_code == 422


def test_fixture_files_cannot_escape_the_fixture_dir():
    key = FIXTURE_IDS[0]
    assert client.get(f"/fixtures/{key}/..%2f..%2fmock-ats%2fmock_ats.py").status_code == 404
    assert client.get("/fixtures/greenhouse/does-not-exist/").status_code == 404


# --- Optional: render every fixture in real Chromium, with every other host blocked -------


def _chromium():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    pw = sync_playwright().start()
    try:
        return pw, pw.chromium.launch()
    except Exception:  # noqa: BLE001 - browser binaries not installed
        pw.stop()
        return None


@pytest.fixture(scope="module")
def live_mock():
    import uvicorn

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", ws="none"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    started = _chromium()
    if started is None:
        pytest.skip("Playwright Chromium is not installed (pip install playwright; python -m playwright install chromium)")
    pw, b = started
    yield b
    b.close()
    pw.stop()


@pytest.mark.parametrize("key", FIXTURE_IDS)
def test_fixture_renders_and_submits_in_chromium_offline(key, live_mock, browser, tmp_path):
    context = browser.new_context()
    escaped: list[str] = []

    def guard(route):
        if route.request.url.startswith(live_mock):
            return route.continue_()
        escaped.append(route.request.url)
        return route.abort()

    context.route("**/*", guard)
    page = context.new_page()
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(RESUME)
    try:
        page.goto(f"{live_mock}/fixtures/{key}/", wait_until="load")
        meta = json.loads((FIXTURES[key] / "meta.json").read_text(encoding="utf-8"))
        frame = page.frame_locator("iframe").first if meta.get("frame") else page
        form = frame.locator("form:has(input[type=file])").first
        form.wait_for(state="attached", timeout=5000)
        assert form.locator("input, select, textarea").count() >= 3
        form.locator("input[type=file]").first.set_input_files(str(resume))
        SUBMISSIONS.clear()
        form.evaluate("f => HTMLFormElement.prototype.submit.call(f)")  # bypass required-field validation; we test transport
        target = page.frame_locator("iframe").first if meta.get("frame") else page
        target.locator("#application_confirmation").wait_for(timeout=5000)
        assert escaped == [], f"fixture tried to reach other hosts: {escaped[:5]}"
        [rec] = [s for s in SUBMISSIONS if s["fixture"] == key]
        assert rec["files"][0]["sha256"] == hashlib.sha256(RESUME).hexdigest()
    finally:
        context.close()
