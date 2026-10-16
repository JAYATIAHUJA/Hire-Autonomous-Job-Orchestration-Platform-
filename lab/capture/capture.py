"""Capture public job application forms as offline fixtures for the mock ATS lab.

For each target in targets.json this loads the public application page in headless
Chromium, waits for the form to render, and saves the *rendered* DOM (Lever and Ashby
render client-side) with only the stylesheets it needs, under
lab/fixtures/<ats>/<company>-<reqid>/.

Safety, enforced in code rather than by convention:
- Every non-GET request the page tries to make is aborted, so nothing can be submitted.
- The script never clicks, types into, or submits anything. It only loads and reads.
- Saved pages have every <script>, <iframe>, <noscript>, inline event handler, preload hint
  and tracking pixel removed. Every <form action> points at the mock's /submit, and every
  outbound link is neutralised, so a fixture opened offline cannot reach the employer.
- Images, fonts and media are not downloaded: the lab needs the form, not the branding.

    python lab/capture/capture.py lab/capture/targets.json            # all targets
    python lab/capture/capture.py lab/capture/targets.json --only lever # one ATS
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.sync_api import Route, sync_playwright  # noqa: E402

from polite import USER_AGENT, PoliteSession, Throttle  # noqa: E402

LAB = Path(__file__).resolve().parent.parent
FIXTURES = LAB / "fixtures"

# Hosts whose scripts render the form. Everything else is third-party and is blocked at capture time.
RENDER_HOSTS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "ashbyprd.com",
)
BLOCKED_TYPES = {"image", "font", "media"}

SANITISE_JS = r"""
({fixtureId, sheets}) => {
  const doc = document;
  // 1. Linked stylesheets become same-origin <style> copies (so their rules can be pruned
  //    below); they go back out as local assets/ files at the end. Unknown ones are dropped.
  const byHref = Object.fromEntries(sheets.map(s => [s.href, s]));
  for (const el of doc.querySelectorAll('link[rel~="stylesheet"]')) {
    const sheet = byHref[el.href];
    if (sheet) {
      const style = doc.createElement('style');
      style.setAttribute('data-lab-asset', sheet.local);
      if (el.media) style.media = el.media;
      style.textContent = sheet.css;
      el.replaceWith(style);
    } else {
      el.remove();
    }
  }
  // 2. Freeze current control values the user cannot have typed (we typed nothing) and name
  //    unnamed controls so a plain form post carries them.
  let n = 0;
  for (const el of doc.querySelectorAll('input, select, textarea')) {
    if (!el.getAttribute('name')) {
      const fallback = el.id || el.getAttribute('aria-label') || ('lab_field_' + (n++));
      el.setAttribute('name', fallback);
      el.setAttribute('data-lab-named', '1');
    }
  }
  // 3. Remove everything executable or third-party.
  const kill = 'script, noscript, iframe, object, embed, template, link[rel~="preload"], ' +
    'link[rel~="modulepreload"], link[rel~="prefetch"], link[rel~="preconnect"], ' +
    'link[rel~="dns-prefetch"], link[rel~="manifest"], link[rel~="icon"], link[rel~="apple-touch-icon"], ' +
    'link[rel~="canonical"], link[rel~="alternate"], meta[http-equiv="refresh"], base';
  for (const el of doc.querySelectorAll(kill)) el.remove();
  for (const el of doc.querySelectorAll('*')) {
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase();
      if (name.startsWith('on') || name === 'srcset' || name === 'integrity' || name === 'nonce' ||
          name === 'formaction' || name === 'ping') el.removeAttribute(attr.name);
    }
    const style = el.getAttribute('style');
    if (style && /url\(/i.test(style)) el.setAttribute('style', style.replace(/url\((?!\s*['"]?data:)[^)]*\)/gi, 'none'));
  }
  // 4. Media: keep only inline data: images, so the layout stays but nothing is fetched.
  for (const el of doc.querySelectorAll('img, source, video, audio, input[type="image"]')) {
    const src = el.getAttribute('src') || '';
    if (!src.startsWith('data:')) {
      el.removeAttribute('src');
      if (el.tagName === 'IMG') el.setAttribute('src', 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==');
      el.setAttribute('data-lab-stripped', 'src');
    }
  }
  for (const el of doc.querySelectorAll('svg image, use')) {
    for (const a of ['href', 'xlink:href']) {
      const v = el.getAttribute(a) || '';
      if (v && !v.startsWith('#')) el.removeAttribute(a);
    }
  }
  // 6. Links cannot leave the fixture.
  for (const el of doc.querySelectorAll('a[href], area[href]')) {
    const href = el.getAttribute('href');
    if (!href.startsWith('#')) { el.setAttribute('data-lab-href', el.href); el.setAttribute('href', '#'); }
    el.removeAttribute('target');
  }
  // 7. Every form posts to the mock. If the ATS renders its form without a <form>
  //    element (React state only), wrap the controls so a scripted submit still works.
  let forms = Array.from(doc.querySelectorAll('form'));
  if (!forms.some(f => f.querySelector('input, select, textarea'))) {
    const fileInput = doc.querySelector('input[type="file"]');
    let host = fileInput || doc.querySelector('input, select, textarea');
    if (host) {
      // climb to the smallest ancestor that holds (almost) all the controls
      const total = doc.querySelectorAll('input, select, textarea').length;
      while (host.parentElement && host.querySelectorAll('input, select, textarea').length < total * 0.9) {
        host = host.parentElement;
      }
      const form = doc.createElement('form');
      form.setAttribute('data-lab-wrapped', '1');
      host.parentNode.insertBefore(form, host);
      form.appendChild(host);
      forms = [form];
    }
  }
  for (const form of forms) {
    if (form.getAttribute('data-lab-orig-action') === null) {
      form.setAttribute('data-lab-orig-action', form.getAttribute('action') || '');
    }
    form.setAttribute('action', '/submit');
    form.setAttribute('method', 'post');
    form.setAttribute('enctype', 'multipart/form-data');
    form.removeAttribute('target');
    if (!form.querySelector('input[name="_lab_fixture"]')) {
      const tag = doc.createElement('input');
      tag.type = 'hidden'; tag.name = '_lab_fixture'; tag.value = fixtureId;
      form.prepend(tag);
    }
    // the visible submit button must actually submit the (mock) form
    const btn = form.querySelector('button[type="submit"], input[type="submit"]') ||
      Array.from(form.querySelectorAll('button')).find(b => /submit|apply|send/i.test(b.textContent));
    if (btn) { btn.setAttribute('type', 'submit'); btn.setAttribute('data-lab-submit', '1'); btn.removeAttribute('disabled'); }
  }
  // 8. Prune CSS to the rules that match the saved DOM (pseudo-classes ignored, so hover and
  //    focus styles of present elements stay). Unparseable selectors are kept. CSS-in-JS rules
  //    that live only in the CSSOM (insertRule) are written out as text here too.
  const keepSelector = sel => {
    const bare = sel.replace(/::?[a-zA-Z-]+(\((?:[^()]|\([^()]*\))*\))?/g, '').trim();
    if (!bare || /^[>+~*\s]*$/.test(bare)) return true;
    try { return doc.querySelector(bare) !== null; } catch (e) { return true; }
  };
  const prune = rules => {
    const out = [];
    for (const r of Array.from(rules)) {
      if (r instanceof CSSStyleRule) {
        if (r.selectorText.split(',').some(keepSelector)) out.push(r.cssText);
      } else if (r instanceof CSSFontFaceRule || r instanceof CSSImportRule) {
        continue;
      } else if (r instanceof CSSKeyframesRule) {
        out.push(r.cssText);
      } else if (r.cssRules) {  // @media, @supports, @layer, @container
        const inner = prune(r.cssRules);
        if (inner) out.push(r.cssText.slice(0, r.cssText.indexOf('{')) + '{\n' + inner + '\n}');
      } else {
        out.push(r.cssText);
      }
    }
    return out.join('\n');
  };
  const assets = {};
  for (const el of Array.from(doc.querySelectorAll('style'))) {
    let text = el.textContent;
    try { if (el.sheet) text = prune(el.sheet.cssRules); } catch (e) {}
    const local = el.getAttribute('data-lab-asset');
    if (local) {
      assets[local] = text;
      const link = doc.createElement('link');
      link.rel = 'stylesheet';
      link.setAttribute('href', local);
      if (el.media) link.media = el.media;
      el.replaceWith(link);
    } else {
      el.textContent = text;
    }
  }
  // 9. Field inventory for meta.json.
  const controls = Array.from(doc.querySelectorAll('input, select, textarea'))
    .filter(el => !['hidden', 'submit', 'button', 'reset', 'image'].includes((el.type || '').toLowerCase()));
  const labelFor = el => {
    const byFor = el.id && doc.querySelector('label[for="' + CSS.escape(el.id) + '"]');
    const t = (byFor && byFor.textContent) || el.getAttribute('aria-label') ||
      (el.closest('label') && el.closest('label').textContent) || el.getAttribute('placeholder') || '';
    return t.replace(/\s+/g, ' ').trim().slice(0, 160);
  };
  const fields = controls.map(el => ({
    name: el.getAttribute('name'), tag: el.tagName.toLowerCase(), type: (el.type || '').toLowerCase(),
    role: el.getAttribute('role') || '', required: el.required || el.getAttribute('aria-required') === 'true',
    label: labelFor(el),
  }));
  doc.documentElement.setAttribute('data-lab-fixture', fixtureId);
  return {html: '<!doctype html>\n' + doc.documentElement.outerHTML, fields, assets};
}
"""

THIRD_PARTY_HINT = re.compile(
    r"google-analytics|googletagmanager|gtag|segment\.(com|io)|hotjar|hcaptcha|recaptcha|datadog|sentry|"
    r"intercom|onetrust|cookielaw|facebook|linkedin\.com/px|doubleclick|clarity\.ms|fullstory|amplitude|mixpanel",
    re.I,
)

NOTABLE = [
    ("cover_letter_upload", re.compile(r"cover letter", re.I)),
    ("how_did_you_hear", re.compile(r"how did you hear|hear about|referr|source", re.I)),
    ("work_authorisation", re.compile(r"authori[sz]|visa|sponsor|right to work|work permit", re.I)),
    ("eeo_demographics", re.compile(r"gender|race|ethnic|veteran|disabilit|pronoun|sexual orientation|demographic", re.I)),
    ("location", re.compile(r"\blocation\b|city|where are you based|current(ly)? (based|located)", re.I)),
    ("notice_period", re.compile(r"notice period|notice", re.I)),
    ("salary_ctc", re.compile(r"salary|ctc|compensation|expected pay", re.I)),
    ("linkedin_url", re.compile(r"linkedin", re.I)),
    ("github_or_portfolio", re.compile(r"github|portfolio|website", re.I)),
    ("consent_privacy", re.compile(r"consent|privacy|gdpr|data processing", re.I)),
]


def clean_css(css: str) -> str:
    css = re.sub(r"@font-face\s*\{[^}]*\}", "", css, flags=re.I)
    css = re.sub(r"@import[^;]+;", "", css, flags=re.I)
    css = re.sub(r"/\*# sourceMappingURL=[^*]*\*/", "", css)
    # url("..."), url('...') or url(...): drop every reference except inline data: URIs
    url = re.compile(r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)'"]*))\s*\)""", re.I)
    return url.sub(lambda m: m.group(0) if (m.group(1) or m.group(2) or m.group(3) or "").startswith("data:")
                   else "none", css)


def notable_fields(fields: list[dict], questions: dict | None) -> list[str]:
    labels = [f["label"] for f in fields]
    if questions:
        labels += [q.get("label", "") for q in questions.get("questions", [])]
        labels += [q.get("label", "") for q in questions.get("location_questions", [])]
        labels.append(json.dumps(questions.get("compliance") or [])[:4000])
        labels.append(json.dumps(questions.get("demographic_questions") or {})[:4000])
    text = "\n".join(labels)
    out = [key for key, rx in NOTABLE if rx.search(text)]
    files = sum(1 for f in fields if f["type"] == "file")
    if files >= 2:
        out.append("multi_file_upload")
    if any(f["tag"] == "select" or f["role"] == "combobox" for f in fields):
        out.append("dropdowns")
    if any(f["type"] in ("radio", "checkbox") for f in fields):
        out.append("radio_or_checkbox")
    if any(f["tag"] == "textarea" for f in fields):
        out.append("free_text")
    custom = [f for f in fields if re.match(r"(question_|cards\[|[0-9a-f]{8}-)", f["name"] or "")]
    if custom or (questions and any(str(q.get("fields", [{}])[0].get("name", "")).startswith("question_")
                                    for q in questions.get("questions", []))):
        out.append("custom_questions")
    return out


def is_read_only_graphql(url: str, body: str | None) -> bool:
    """Ashby's job page loads the posting and its form definition with GraphQL *queries* sent
    as POST. Those are reads and are let through. Anything else (mutations, uploads, form
    posts) is not, which is what keeps a capture from ever submitting an application."""
    parsed = urlparse(url)
    if not (parsed.hostname or "").endswith("ashbyhq.com") or parsed.path != "/api/non-user-graphql":
        return False
    try:
        payload = json.loads(body or "")
    except ValueError:
        return False
    ops = payload if isinstance(payload, list) else [payload]
    return all(
        isinstance(op, dict) and re.match(r"\s*query\b", op.get("query") or "") and "mutation" not in op["query"]
        for op in ops
    )


def _route(route: Route, throttle: Throttle) -> None:
    req = route.request
    host = urlparse(req.url).hostname or ""
    if req.method not in ("GET", "HEAD") and not is_read_only_graphql(req.url, req.post_data):
        return route.abort()  # never send anything to the employer
    if req.resource_type in BLOCKED_TYPES or THIRD_PARTY_HINT.search(req.url):
        return route.abort()
    # Third-party scripts and XHR are not needed to render the form. CDN stylesheets are kept.
    if req.resource_type != "stylesheet" and not host.endswith(RENDER_HOSTS):
        return route.abort()
    throttle.wait()
    return route.continue_()


def capture_one(browser, http: PoliteSession, throttle: Throttle, target: dict) -> dict:
    ats, fixture = target["ats"], target["fixture"]
    out_dir = FIXTURES / ats / fixture
    out_dir.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(user_agent=USER_AGENT, locale="en-IN", viewport={"width": 1280, "height": 1600})
    context.route("**/*", lambda route: _route(route, throttle))
    page = context.new_page()
    css_bodies: dict[str, str] = {}

    def on_response(resp):
        if resp.request.resource_type == "stylesheet" and resp.ok:
            try:
                css_bodies[resp.url] = resp.text()
            except Exception:  # noqa: BLE001 - a missing stylesheet only costs looks
                pass

    page.on("response", on_response)
    url = target["capture_url"]
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("input[type=file], form input, [class*=application] input", timeout=30000)
    except Exception:  # noqa: BLE001
        print(f"  ! no form control appeared on {url}", file=sys.stderr)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(1500)
    final_url = page.url
    page_title = page.title()

    sheets = []
    hrefs = page.eval_on_selector_all('link[rel~="stylesheet"]', "els => els.map(e => e.href)")
    for i, href in enumerate(dict.fromkeys(hrefs)):
        body = css_bodies.get(href)
        if body is None:
            resp = http.get(href)
            body = resp.text if resp is not None and resp.ok else None
        if body is not None:
            sheets.append({"href": href, "css": clean_css(body), "local": f"assets/style-{i}.css"})

    result = page.evaluate(SANITISE_JS, {"fixtureId": f"{ats}/{fixture}", "sheets": sheets})
    context.close()

    (out_dir / "assets").mkdir(exist_ok=True)
    for old in out_dir.glob("assets/*.css"):
        old.unlink()
    for local, text in result["assets"].items():
        (out_dir / local).write_text(text, encoding="utf-8")

    entry = "page.html"
    html = result["html"]
    if target.get("embed"):
        (out_dir / "frame.html").write_text(html, encoding="utf-8")
        html = embed_wrapper({**target, "title": target.get("title") or page_title})
    (out_dir / entry).write_text(html, encoding="utf-8")

    questions = None
    if ats == "greenhouse":
        resp = http.get(f"https://boards-api.greenhouse.io/v1/boards/{target['slug']}/jobs/{target['id']}?questions=true")
        if resp is not None and resp.ok:
            questions = resp.json()
            questions.pop("content", None)  # the job description is not needed for form tests
            (out_dir / "questions.json").write_text(json.dumps(questions, indent=1, ensure_ascii=False), encoding="utf-8")

    fields = result["fields"]
    meta = {
        "url": target["url"],
        "captured_from": url,
        "final_url": final_url,
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "ats": ats,
        "company": target["slug"],
        "req_id": target["id"],
        "title": target.get("title") or page_title,
        "location": target.get("location") or ((questions or {}).get("location") or {}).get("name", ""),
        "variant": target.get("variant", ""),
        "entry": entry,
        "frame": "frame.html" if target.get("embed") else None,
        "field_count": len(fields),
        "required_count": sum(1 for f in fields if f["required"]),
        "file_inputs": sum(1 for f in fields if f["type"] == "file"),
        "notable_fields": notable_fields(fields, questions),
        "fields": fields,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return meta


def embed_wrapper(target: dict) -> str:
    """A stand-in company careers page that embeds the Greenhouse form in an iframe, as real
    careers sites do with the Greenhouse embed snippet. Only the iframe content is captured."""
    title = target.get("title", "Open role")
    return f"""<!doctype html>
<html lang="en" data-lab-fixture="greenhouse/{target['fixture']}"><head><meta charset="utf-8">
<title>Careers - {title}</title>
<style>body{{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9}}header{{padding:24px 32px;background:#1f2937;color:#fff}}
main{{max-width:960px;margin:0 auto;padding:24px}}iframe{{width:100%;height:2600px;border:0;background:#fff}}</style>
</head><body>
<header><strong>{target['slug']}</strong> careers (lab stand-in page; the iframe below is the captured Greenhouse embed)</header>
<main><h1>{title}</h1>
<div id="grnhse_app"><iframe id="grnhse_iframe" title="Greenhouse Job Board" src="frame.html"></iframe></div>
</main></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets")
    ap.add_argument("--only", help="capture only this ATS")
    ap.add_argument("--fixture", help="capture only this fixture id")
    args = ap.parse_args()
    targets = json.loads(Path(args.targets).read_text(encoding="utf-8"))
    throttle = Throttle()
    http = PoliteSession(throttle)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for t in targets:
            if (args.only and t["ats"] != args.only) or (args.fixture and t["fixture"] != args.fixture):
                continue
            print(f"{t['ats']}/{t['fixture']} <- {t['capture_url']}", file=sys.stderr)
            try:
                meta = capture_one(browser, http, throttle, t)
            except Exception as exc:  # noqa: BLE001 - one dead posting should not stop the run
                print(f"  ! capture failed: {exc}", file=sys.stderr)
                continue
            print(f"  fields={meta['field_count']} files={meta['file_inputs']} notable={meta['notable_fields']}",
                  file=sys.stderr)
        browser.close()


if __name__ == "__main__":
    main()
