"""Probe candidate employers for public Greenhouse, Lever and Ashby job boards.

    python scripts/ats_registry/probe.py                 # all of candidates.txt
    python scripts/ats_registry/probe.py --limit 20      # quick try
    python scripts/ats_registry/probe.py --only Razorpay --only Postman
    python scripts/ats_registry/probe.py --boards data/ats-registry/discovered-boards.txt

Two inputs: candidates.txt (company names; slugs are guessed) and, with --boards, known
"ats:slug" boards from discover.py (one request each; the name comes from the board).

Writes, next to candidates.txt:
    registry.json               boards with at least one India-located opening (the seed)
    boards-without-india.json   boards that exist but list nothing in India today
    probe-summary.json          hit rates per ATS and run stats

Polite by design: at most --rate requests per second to each ATS host, a contact
User-Agent, and every response cached under .cache/ (gitignored), so a re-run or an
interrupted run resumes without asking again. Delete .cache/ to re-probe from scratch.
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import httpx  # noqa: E402

from app.jobs.ats_registry import (  # noqa: E402
    ATS_VENDORS,
    HostRateLimiter,
    ResponseCache,
    entries_to_json,
    merge_entries,
    parse_boards,
    parse_candidates,
    probe_board,
    probe_candidate,
    sort_registry,
)

DATA = ROOT / "data" / "ats-registry"
USER_AGENT = "HireRegistryProbe/0.1 (+https://github.com/JAYATIAHUJA/Hire-Autonomous-Job-Orchestration-Platform-)"


async def run(args: argparse.Namespace) -> int:
    candidates = parse_candidates(Path(args.candidates).read_text(encoding="utf-8"))
    if args.only:
        wanted = {n.lower() for n in args.only}
        candidates = [c for c in candidates if c.name.lower() in wanted]
    boards = parse_boards(Path(args.boards).read_text(encoding="utf-8")) if args.boards else []
    if args.limit:
        candidates = candidates[: args.limit]
        boards = boards[: args.limit]
    total = len(candidates) + len(boards)

    limiter = HostRateLimiter(args.rate)
    cache = ResponseCache(Path(args.cache))
    sem = asyncio.Semaphore(args.concurrency)
    done = 0

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
    ) as client:

        async def one(probe):
            nonlocal done
            async with sem:
                res = await probe
            done += 1
            if res.entry:
                e = res.entry
                print(f"[{done}/{total}] {e.name}: {e.ats}/{e.board_token} "
                      f"({e.india_openings} in India of {e.total_openings})", flush=True)
            elif done % 100 == 0:
                print(f"[{done}/{total}] ...", flush=True)
            return res

        by_name = await asyncio.gather(
            *(one(probe_candidate(client, c, limiter=limiter, cache=cache)) for c in candidates)
        )
        by_board = await asyncio.gather(
            *(one(probe_board(client, ats, slug, limiter=limiter, cache=cache)) for ats, slug in boards)
        )

    results = [*by_name, *by_board]
    hits = sort_registry(merge_entries(
        (r.entry for r in by_name if r.entry), (r.entry for r in by_board if r.entry)
    ))
    hit_keys = {(e.ats, e.board_token) for e in hits}
    no_india = sort_registry(
        b for b in merge_entries(*(r.boards_without_india for r in results))
        if (b.ats, b.board_token) not in hit_keys
    )
    errors = [r.candidate.name for r in results if r.errors and not r.entry]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "registry.json").write_text(entries_to_json(hits), encoding="utf-8")
    # Thousands of boards: keep only those hiring elsewhere today, with what a later
    # re-probe or a remote-roles pass needs.
    slim = [
        {"name": b.name, "ats": b.ats, "board_token": b.board_token,
         "total_openings": b.total_openings, "remote_openings": b.remote_openings}
        for b in no_india
        if b.total_openings > 0  # empty boards stay findable via discovered-boards.txt
    ]
    (out / "boards-without-india.json").write_text(
        "[\n" + ",\n".join(json.dumps(s, ensure_ascii=False) for s in slim) + "\n]\n", encoding="utf-8"
    )

    per_ats = Counter(e.ats for e in hits)
    name_hits = sum(1 for r in by_name if r.entry)
    summary = {
        "candidates": len(candidates),
        "candidates_with_india_board": name_hits,
        "candidate_hit_rate": round(name_hits / len(candidates), 3) if candidates else None,
        "discovered_boards_probed": len(boards),
        "discovered_boards_with_india": sum(1 for r in by_board if r.entry),
        "boards_with_india_openings": len(hits),
        "boards_without_india_openings": len(no_india),
        "per_ats": {ats: per_ats.get(ats, 0) for ats in ATS_VENDORS},
        "per_source": Counter(e.source for e in hits),
        "india_openings_total": sum(e.india_openings for e in hits),
        "name_verified": Counter(str(e.name_verified) for e in hits),
        "requests": sum(r.requests for r in results),
        "candidates_with_errors": errors,
    }
    (out / "probe-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"Verified boards with India openings: {len(hits)} "
          f"({', '.join(f'{a} {per_ats.get(a, 0)}' for a in ATS_VENDORS)})")
    print(f"India openings across them: {summary['india_openings_total']}")
    print(f"Boards with no India opening today: {len(no_india)}")
    print(f"Requests: {summary['requests']}; candidates with network errors: {len(errors)}")
    if errors:
        print("  re-run to retry:", ", ".join(errors[:15]), "..." if len(errors) > 15 else "")
    return 0


def main() -> int:
    # Board names can hold any Unicode; a Windows console's code page can't print all of it.
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidates", default=str(DATA / "candidates.txt"))
    parser.add_argument("--boards", default="", help="discovered-boards.txt from discover.py")
    parser.add_argument("--out", default=str(DATA))
    parser.add_argument("--cache", default=str(DATA / ".cache"))
    parser.add_argument("--rate", type=float, default=2.0, help="max requests/second per ATS host")
    parser.add_argument("--concurrency", type=int, default=8, help="companies probed at once")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", action="append", default=[], help="probe just this company (repeatable)")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
