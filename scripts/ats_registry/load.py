"""Load data/ats-registry/registry.json into the companies table.

    python scripts/ats_registry/load.py                       # uses DATABASE_URL
    DATABASE_URL=postgresql+psycopg://... python scripts/ats_registry/load.py

On Postgres, run the migrations first (alembic upgrade head). Safe to re-run:
companies are matched by (ats_vendor, ats_board_token), then by name.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.db import SessionLocal, init_db  # noqa: E402
from app.jobs.ats_registry import load_registry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", default=str(ROOT / "data" / "ats-registry" / "registry.json"))
    args = parser.parse_args()

    entries = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    init_db()
    db = SessionLocal()
    try:
        stats = load_registry(db, entries)
    finally:
        db.close()
    print(f"companies: {stats['created']} created, {stats['updated']} updated ({len(entries)} boards)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
