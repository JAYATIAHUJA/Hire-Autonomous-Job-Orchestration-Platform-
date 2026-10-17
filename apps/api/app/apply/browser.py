"""Fill (and, when told to, submit) a Greenhouse form in a headless Chromium.

Shared by the worker's apply runs and scripts/apply/apply.py. Every value is read back
from the page after it is typed; any mismatch stops the run. CAPTCHAs are never solved.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

CONFIRM_SELECTORS = ["#application_confirmation", "text=/thank you for applying/i", "text=/application (has been )?(submitted|received)/i"]
SUBMIT_SELECTORS = ["#submit_app", "button[type=submit]", "button:has-text('Submit application')", "input[type=submit]"]
CAPTCHA_SELECTOR = "iframe[src*='recaptcha'][title*='challenge'], iframe[title*='captcha' i]"


def _targets(page):
    """The page itself, then its iframes: employers that embed Greenhouse's widget
    (payoneer.com and friends) keep every field inside an iframe."""
    yield page
    for frame in page.frames:
        if frame is not page.main_frame:
            yield frame


def _find(page, name):
    """(first matching locator, the page or frame that owns it) or (None, None)."""
    for sel in (f"#{name}", f"[name='{name}']", f"[name='job_application[{name}]']",
                f"#candidate-{name}"):  # new Greenhouse forms: ids only (candidate-location)
        for target in _targets(page):
            loc = target.locator(sel)
            if loc.count():
                return loc.first, target
    return None, None


def field_locator(page, name):
    loc, _ = _find(page, name)
    return loc


def _any(page, selectors):
    for sel in selectors:
        for target in _targets(page):
            if target.locator(sel).count():
                return target.locator(sel).first
    return None


def wait_for_fields(page, answers, seconds: float = 15) -> None:
    """SPA careers pages and embedded iframes render late; give the fields a moment."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if any(field_locator(page, a.field_name) for a in answers):
            return
        page.wait_for_timeout(500)


def _digits(text: str) -> str:
    return "".join(ch for ch in str(text) if ch.isdigit())


def fill_one(page, answer) -> str:
    """Fill one field and read it back. Returns '' when it worked, else the problem."""
    loc, owner = _find(page, answer.field_name)
    if loc is None:
        return f"field not found on the page: {answer.label} ({answer.field_name})"
    kind = answer.field_type
    if kind == "input_file":
        loc.set_input_files(answer.value)
        return ""
    if kind in ("input_text", "textarea"):
        loc.fill(str(answer.value))
        got = loc.input_value()
        if answer.field_name == "phone" or loc.get_attribute("type") == "tel":
            # Phone widgets reformat what was typed (+91 85880 77790); the digits must agree.
            return "" if _digits(got) == _digits(answer.value) else f"{answer.label}: page shows {got!r}"
        return "" if got == str(answer.value) else f"{answer.label}: page shows {got!r}"
    if kind == "multi_value_single_select":
        tag = loc.evaluate("el => el.tagName.toLowerCase()")
        if tag == "select":
            loc.select_option(value=str(answer.value))
            got = loc.input_value()
            return "" if got == str(answer.value) else f"{answer.label}: selected {got!r}"
        # Greenhouse's new forms use a searchable combobox: type the option, pick it.
        # The option list opens in the same page or iframe as the field.
        loc.click()
        loc.fill(answer.shown)
        option = owner.get_by_role("option", name=answer.shown, exact=True)
        if not option.count():
            return f"{answer.label}: option {answer.shown!r} not offered"
        option.first.click()
        return ""
    return f"{answer.label}: can't fill a {kind} field yet"


def wait_for_confirmation(page, seconds: int) -> bool:
    """Poll for a thank-you page for up to `seconds`."""
    for _ in range(seconds):
        if _any(page, CONFIRM_SELECTORS) is not None:
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
             confirm_seconds: int = 30, on_action=None, screenshot_every: int = 0,
             on_screenshot=None) -> FormResult:
    """Open the form, fill every planned answer, and submit only when ``submit`` is True.

    ``on_action(answer, ok, problem)`` fires after each field so callers can show live
    progress; every ``screenshot_every`` successful fields a fresh screenshot is passed
    to ``on_screenshot(bytes)`` for the same reason.
    """
    from playwright.sync_api import sync_playwright

    def notify(answer, ok, problem=""):
        if on_action is not None:
            on_action(answer, ok, problem)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(form_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_load_state("networkidle", timeout=30_000)
            wait_for_fields(page, answers)
            errors = []
            done = 0
            for a in answers:
                problem = fill_one(page, a)
                if problem:
                    errors.append(problem)
                    notify(a, False, problem)
                else:
                    done += 1
                    notify(a, True)
                    if screenshot_every and done % screenshot_every == 0 and on_screenshot is not None:
                        on_screenshot(page.screenshot(full_page=True))
            shot = page.screenshot(full_page=True)
            if errors:
                return FormResult("fill_failed", errors, shot)
            if not submit:
                return FormResult("filled", [], shot)
            button = _any(page, SUBMIT_SELECTORS)
            if button is None:
                return FormResult("no_submit_button", ["Couldn't find the submit button."], shot)
            button.click()
            confirmed = wait_for_confirmation(page, confirm_seconds)
            after = page.screenshot(full_page=True)
            if confirmed:
                return FormResult("submitted", [], after)
            if _any(page, [CAPTCHA_SELECTOR]) is not None:
                return FormResult("captcha", ["The site asked for a CAPTCHA."], after)
            return FormResult("unconfirmed", ["No confirmation page appeared."], after)
        finally:
            browser.close()
