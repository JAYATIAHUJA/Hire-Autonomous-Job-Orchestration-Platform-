"""Fill (and, when told to, submit) a Greenhouse form in a headless Chromium.

Shared by the worker's apply runs and scripts/apply/apply.py. Every value is read back
from the page after it is typed; any mismatch stops the run. CAPTCHAs are never solved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

CONFIRM_SELECTORS = ["#application_confirmation", "text=/thank you for applying/i", "text=/application (has been )?(submitted|received)/i"]
SUBMIT_SELECTORS = ["#submit_app", "button[type=submit]", "button:has-text('Submit application')", "input[type=submit]"]
CAPTCHA_SELECTOR = "iframe[src*='recaptcha'][title*='challenge'], iframe[src*='hcaptcha'], iframe[title*='captcha' i]"


def field_locator(page, name: str):
    for sel in (f"#{name}", f"[name='{name}']", f"[name='job_application[{name}]']"):
        loc = page.locator(sel)
        if loc.count():
            return loc.first
    return None


def fill_one(page, answer) -> str:
    """Fill one field and read it back. Returns '' when it worked, else the problem."""
    loc = field_locator(page, answer.field_name)
    if loc is None:
        return f"field not found on the page: {answer.label} ({answer.field_name})"
    kind = answer.field_type
    if kind == "input_file":
        loc.set_input_files(answer.value)
        return ""
    if kind in ("input_text", "textarea"):
        loc.fill(str(answer.value))
        got = loc.input_value()
        return "" if got == str(answer.value) else f"{answer.label}: page shows {got!r}"
    if kind == "multi_value_single_select":
        tag = loc.evaluate("el => el.tagName.toLowerCase()")
        if tag == "select":
            loc.select_option(value=str(answer.value))
            got = loc.input_value()
            return "" if got == str(answer.value) else f"{answer.label}: selected {got!r}"
        # Greenhouse's new forms use a searchable combobox: type the option, pick it.
        loc.click()
        loc.fill(answer.shown)
        option = page.get_by_role("option", name=answer.shown, exact=True)
        if not option.count():
            return f"{answer.label}: option {answer.shown!r} not offered"
        option.first.click()
        return ""
    return f"{answer.label}: can't fill a {kind} field yet"


def wait_for_confirmation(page, seconds: int) -> bool:
    """Poll for a thank-you page for up to `seconds`."""
    for _ in range(seconds):
        if any(page.locator(s).count() for s in CONFIRM_SELECTORS):
            return True
        page.wait_for_timeout(1000)
    return False


@dataclass
class FormResult:
    # filled | fill_failed | submitted | captcha | unconfirmed | no_submit_button
    status: str
    errors: list[str] = field(default_factory=list)
    screenshot: Optional[bytes] = None


def run_form(form_url: str, answers: list[Any], *, submit: bool, headless: bool = True,
             confirm_seconds: int = 30) -> FormResult:
    """Open the form, fill every planned answer, and submit only when ``submit`` is True."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(form_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_load_state("networkidle", timeout=30_000)
            errors = [e for e in (fill_one(page, a) for a in answers) if e]
            shot = page.screenshot(full_page=True)
            if errors:
                return FormResult("fill_failed", errors, shot)
            if not submit:
                return FormResult("filled", [], shot)
            button = next((page.locator(s).first for s in SUBMIT_SELECTORS if page.locator(s).count()), None)
            if button is None:
                return FormResult("no_submit_button", ["Couldn't find the submit button."], shot)
            button.click()
            confirmed = wait_for_confirmation(page, confirm_seconds)
            after = page.screenshot(full_page=True)
            if confirmed:
                return FormResult("submitted", [], after)
            if page.locator(CAPTCHA_SELECTOR).count():
                return FormResult("captcha", ["The site asked for a CAPTCHA."], after)
            return FormResult("unconfirmed", ["No confirmation page appeared."], after)
        finally:
            browser.close()
