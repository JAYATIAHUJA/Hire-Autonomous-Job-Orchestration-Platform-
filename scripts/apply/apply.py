"""Fill a Greenhouse application in a real browser; submit only when you say so.

    python scripts/apply/apply.py <job-url>                      # dry run: fill, screenshot, stop
    python scripts/apply/apply.py <job-url> --submit             # asks you to type the company name
    python scripts/apply/apply.py <job-url> --submit --headed    # watch it; finish a CAPTCHA yourself

The applicant profile is data/private/applicant.json (gitignored; copy
scripts/apply/applicant.example.json). Every run writes plan.json and screenshots to
data/private/runs/<time>-<board>-<job>/.

Safety rules (ADR-005, ADR-006):
- The default is a dry run. Nothing is sent without --submit.
- A real employer needs you to type its name at the prompt; there is no flag to skip
  that. --yes works only against the local mock ATS.
- A required question the profile doesn't answer stops the run before the browser
  opens and writes a question sheet. Answers are never guessed.
- Every planned value is read back from the page before submit; any mismatch stops it.
- CAPTCHAs are never solved or bypassed. With --headed you can complete it yourself.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import httpx  # noqa: E402

from app.apply.browser import CAPTCHA_SELECTOR, SUBMIT_SELECTORS, fill_one, wait_for_confirmation  # noqa: E402
from app.apply.greenhouse import Applicant, Plan, parse_job_url, plan_application, question_sheet, render_plan  # noqa: E402

PRIVATE = ROOT / "data" / "private"
def confirm_real_submit(plan: Plan, yes: bool) -> bool:
    if plan.job.is_mock:
        return yes or input("Type SUBMIT to send to the mock ATS: ").strip() == "SUBMIT"
    print()
    print(f"This sends a REAL application to {plan.company} for '{plan.title}'.")
    print("It can't be taken back. Check the screenshot first.")
    typed = input(f"Type the company name ({plan.company}) to submit, anything else to stop: ").strip()
    return typed.lower() == plan.company.lower()


def main() -> int:
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--profile", default=str(PRIVATE / "applicant.json"))
    parser.add_argument("--submit", action="store_true", help="send it (after a confirmation prompt)")
    parser.add_argument("--headed", action="store_true", help="show the browser")
    parser.add_argument("--yes", action="store_true", help="skip the prompt (mock ATS only)")
    args = parser.parse_args()

    job = parse_job_url(args.url)
    if args.yes and not job.is_mock:
        print("--yes only works against the local mock ATS. Real employers need you to confirm.")
        return 2

    applicant = Applicant.load(Path(args.profile))
    problems = applicant.problems()
    if problems:
        print("Fix the profile first:\n  - " + "\n  - ".join(problems))
        return 2

    resp = httpx.get(job.questions_url, timeout=30)
    if resp.status_code != 200:
        print(f"Couldn't read the form ({resp.status_code}). Is the job still open? {job.form_url}")
        return 1
    plan = plan_application(job, resp.json(), applicant)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = PRIVATE / "runs" / f"{stamp}-{job.board}-{job.job_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "plan.json").write_text(plan.to_json(), encoding="utf-8")
    print(render_plan(plan))
    print()

    if not plan.ready:
        sheet = run_dir / "question-sheet.json"
        sheet.write_text(json.dumps(question_sheet(plan), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Stopped before opening the form. Answer these in your profile's \"answers\": {sheet}")
        return 3

    from playwright.sync_api import sync_playwright

    result = {"status": "dry_run", "job": job.form_url, "run_dir": str(run_dir)}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(job.form_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        errors = [e for e in (fill_one(page, a) for a in plan.answers) if e]
        page.screenshot(path=str(run_dir / "1-filled.png"), full_page=True)
        print(f"Filled form screenshot: {run_dir / '1-filled.png'}")
        if errors:
            result["status"] = "fill_failed"
            result["errors"] = errors
            print("Stopped, not submitted:\n  - " + "\n  - ".join(errors))
        elif not args.submit:
            print("Dry run: nothing was sent. Check the screenshot, then re-run with --submit.")
        elif not confirm_real_submit(plan, args.yes):
            result["status"] = "cancelled"
            print("Not submitted.")
        else:
            button = next((page.locator(s).first for s in SUBMIT_SELECTORS if page.locator(s).count()), None)
            if button is None:
                result["status"] = "no_submit_button"
                print("Couldn't find the submit button. Not submitted.")
            else:
                button.click()
                # Headed, you may be finishing a CAPTCHA by hand, so wait longer.
                confirmed = wait_for_confirmation(page, seconds=300 if args.headed else 30)
                page.screenshot(path=str(run_dir / "2-after-submit.png"), full_page=True)
                if confirmed:
                    result["status"] = "submitted"
                    print(f"Submitted. Confirmation screenshot: {run_dir / '2-after-submit.png'}")
                elif page.locator(CAPTCHA_SELECTOR).count():
                    result["status"] = "captcha"
                    print("The site asked for a CAPTCHA. Hire never solves those: re-run with --headed and finish it yourself.")
                else:
                    result["status"] = "unconfirmed"
                    print("No confirmation seen. Check the screenshot and your email before trying again.")
        browser.close()

    (run_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["status"] in ("dry_run", "submitted") else 1


if __name__ == "__main__":
    sys.exit(main())
