"""Trim job descriptions in already-captured fixtures, without recapturing. Offline: every
request the page makes is aborted. capture.py applies the same step to new captures.

    python lab/capture/trim_descriptions.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from capture import FIXTURES, TRIM_JS, TRIM_NOTE  # noqa: E402


def main() -> None:
    before_total = after_total = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(java_script_enabled=True)
        context.route("**/*", lambda route: route.abort())
        page = context.new_page()
        for path in sorted(FIXTURES.glob("*/*/*.html")):
            html = path.read_text(encoding="utf-8")
            before_total += len(html.encode())
            page.set_content(html, wait_until="domcontentloaded")
            saved = page.evaluate(TRIM_JS, TRIM_NOTE)
            if saved > 0:
                html = "<!doctype html>\n" + page.evaluate("() => document.documentElement.outerHTML")
                path.write_text(html, encoding="utf-8")
                print(f"{path.relative_to(FIXTURES)}: -{saved} chars", file=sys.stderr)
            after_total += len(html.encode())
        browser.close()
    print(f"html total {before_total} -> {after_total} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
