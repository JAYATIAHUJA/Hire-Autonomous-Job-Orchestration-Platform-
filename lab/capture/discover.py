"""Find live public postings on Greenhouse, Lever and Ashby boards that hire in India.

Read-only: it calls only the public board APIs (GET), politely and slowly, and writes
a candidate list to stdout as JSON. It never opens or submits an application form.

    python lab/capture/discover.py --names data/ats-registry/candidates.txt --limit 60 > candidates.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from polite import PoliteSession  # noqa: E402

INDIA = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|pune|hyderabad|chennai|gurgaon|gurugram|noida|delhi|kolkata|ahmedabad)\b",
    re.I,
)

APIS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


def slug_variants(line: str) -> list[str]:
    name, _, extra = line.partition("|")
    base = name.strip().lower()
    variants = [re.sub(r"[^a-z0-9]", "", base), re.sub(r"[^a-z0-9]+", "-", base).strip("-")]
    variants += [s.strip() for s in extra.split(",") if s.strip()]
    return list(dict.fromkeys(v for v in variants if v))


def india_jobs(ats: str, slug: str, payload) -> list[dict]:
    out = []
    if ats == "greenhouse":
        for j in payload.get("jobs", []):
            loc = (j.get("location") or {}).get("name", "")
            if INDIA.search(loc):
                out.append({"id": str(j["id"]), "title": j["title"], "location": loc, "url": j["absolute_url"]})
    elif ats == "lever":
        for j in payload if isinstance(payload, list) else []:
            cats = j.get("categories") or {}
            loc = " / ".join([cats.get("location") or ""] + list(cats.get("allLocations") or []))
            if INDIA.search(loc):
                out.append({"id": j["id"], "title": j["text"], "location": loc, "url": j["hostedUrl"] + "/apply"})
    else:
        for j in payload.get("jobs", []):
            locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
            loc = " / ".join(locs)
            if INDIA.search(loc) and j.get("isListed", True):
                out.append({"id": j["id"], "title": j["title"], "location": loc, "url": j["jobUrl"] + "/application"})
    for j in out:
        j.update(ats=ats, slug=slug)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", required=True)
    ap.add_argument("--limit", type=int, default=60, help="how many names from the top of the file")
    ap.add_argument("--per-board", type=int, default=3)
    args = ap.parse_args()

    lines = [l for l in Path(args.names).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    http = PoliteSession()
    found = []
    for line in lines[: args.limit]:
        for slug in slug_variants(line):
            for ats, tmpl in APIS.items():
                resp = http.get(tmpl.format(slug=slug))
                if resp is None or resp.status_code != 200:
                    continue
                try:
                    jobs = india_jobs(ats, slug, resp.json())
                except ValueError:
                    continue
                if jobs:
                    print(f"{ats:10} {slug:24} {len(jobs)} india jobs", file=sys.stderr)
                    found.extend(jobs[: args.per_board])
    json.dump(found, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
