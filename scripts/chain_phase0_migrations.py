"""One-off: chain the Phase 0 migrations after merging WP3 (ATS registry) into the stack.

WP3 owns revision 0006. The integration migrations written alongside it become 0007
and 0008, giving one line: 0005 -> 0006 (WP3) -> 0007 (account FKs) -> 0008 (consents).

    python scripts/chain_phase0_migrations.py
"""

import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parent.parent / "apps" / "api" / "migrations" / "versions"

# old file name -> (new file name, new revision, new down_revision)
PLAN = [
    ("0007_privacy_consents_and_onboarding.py", "0008_privacy_consents_and_onboarding.py", "0008", "0007"),
    ("0006_account_fks_for_pow_and_facts.py", "0007_account_fks_for_pow_and_facts.py", "0007", "0006"),
    ("0006_companies_ats_board.py", "0006_companies_ats_board.py", "0006", "0005"),
]


def rewrite(text: str, revision: str, down: str) -> str:
    text = re.sub(r"^revision = '[^']*'", f"revision = '{revision}'", text, count=1, flags=re.M)
    text = re.sub(r"^down_revision = '[^']*'", f"down_revision = '{down}'", text, count=1, flags=re.M)
    text = re.sub(r"^Revision ID: .*$", f"Revision ID: {revision}", text, count=1, flags=re.M)
    return re.sub(r"^Revises: .*$", f"Revises: {down}", text, count=1, flags=re.M)


def main() -> None:
    for old, new, revision, down in PLAN:
        src = VERSIONS / old
        if not src.exists():
            raise SystemExit(f"missing {src}: run this after merging WP3 into the Phase 0 stack")
        text = rewrite(src.read_text(encoding="utf-8"), revision, down)
        (VERSIONS / new).write_text(text, encoding="utf-8")
        if new != old:
            src.unlink()
        print(f"{old} -> {new} (revision {revision}, down_revision {down})")


if __name__ == "__main__":
    main()
