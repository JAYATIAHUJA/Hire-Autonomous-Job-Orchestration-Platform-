"""Find real Greenhouse, Lever and Ashby board slugs in the Common Crawl URL index.

    python scripts/ats_registry/discover.py                # 3 latest crawls
    python scripts/ats_registry/discover.py --crawls 5

Guessing slugs from company names (candidates.txt) misses most boards, because many
Indian employers use other ATSs and the ones that don't often use an unguessable slug.
Every slug found here appeared in a real crawled URL, so it exists or existed.
Writes data/ats-registry/discovered-boards.txt ("ats:slug" per line), which probe.py
reads with --boards. It only reads the public index; it never touches the ATS hosts.
"""

import argparse
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "ats-registry" / "discovered-boards.txt"
INDEX = "https://index.commoncrawl.org"

HOSTS = {
    "boards.greenhouse.io": "greenhouse",
    "job-boards.greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "jobs.ashbyhq.com": "ashby",
}
SLUG_RE = re.compile(r"^https?://[^/]+/([A-Za-z0-9._-]+)")
NOT_SLUGS = {"embed", "v1", "robots.txt", "sitemap.xml", "favicon.ico", "api", "careers", "jobs", "static"}


def get(client: httpx.Client, url: str, tries: int = 5) -> str:
    delay = 5.0
    for attempt in range(tries):
        try:
            resp = client.get(url)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 404:
                return ""
        except httpx.HTTPError:
            pass
        if attempt < tries - 1:
            time.sleep(delay)
            delay *= 2
    print(f"  gave up: {url}", file=sys.stderr)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crawls", type=int, default=3, help="how many of the latest crawls to read")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    slugs: set[tuple[str, str]] = set()
    with httpx.Client(timeout=httpx.Timeout(180.0), headers={"User-Agent": "HireRegistryDiscover/0.1"}) as client:
        crawls = [c["id"] for c in httpx.get(f"{INDEX}/collinfo.json", timeout=60).json()[: args.crawls]]
        for crawl in crawls:
            for host, ats in HOSTS.items():
                meta = get(client, f"{INDEX}/{crawl}-index?url={host}/*&showNumPages=true")
                pages = int(re.search(r'"pages":\s*(\d+)', meta).group(1)) if '"pages"' in meta else 0
                before = len(slugs)
                for page in range(pages):
                    text = get(client, f"{INDEX}/{crawl}-index?url={host}/*&output=text&fl=url&page={page}")
                    for line in text.splitlines():
                        m = SLUG_RE.match(line.strip())
                        if m and m.group(1).lower() not in NOT_SLUGS:
                            slugs.add((ats, m.group(1).lower()))
                    time.sleep(1)  # the index is a shared public service
                print(f"{crawl} {host}: {pages} pages, +{len(slugs) - before} slugs", flush=True)

    lines = sorted(f"{ats}:{slug}" for ats, slug in slugs)
    header = (
        "# Board slugs seen in the Common Crawl URL index (scripts/ats_registry/discover.py).\n"
        "# Unverified: probe.py --boards keeps only those that answer and list an India opening.\n"
    )
    Path(args.out).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    counts = {a: sum(1 for x, _ in slugs if x == a) for a in sorted(set(HOSTS.values()))}
    print(f"wrote {len(lines)} slugs to {args.out}: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
