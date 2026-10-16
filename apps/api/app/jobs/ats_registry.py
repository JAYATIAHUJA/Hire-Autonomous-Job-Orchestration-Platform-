"""ATS registry: which employers run a public Greenhouse, Lever or Ashby board.

The registry is the seed list the job readers crawl (PLAN.md §5.4). It is built by
probing each candidate employer's likely board slugs against the public, documented
job-board APIs and keeping only boards that answer and list an India-located opening.

Nothing here is trusted from the candidate list: a board only enters the registry
after a probe saw it. Slugs are guesses, so a hit can belong to a different company
with the same slug; Greenhouse reports the board's company name and we check it,
while Lever and Ashby don't, so their hits are marked ``name_verified=None``.

The probe is used by ``scripts/ats_registry/probe.py`` and the loader by
``scripts/ats_registry/load.py``.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx
from sqlalchemy.orm import Session

from .models import Company

ATS_VENDORS = ("greenhouse", "lever", "ashby")

BOARD_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}

# Words that are part of a legal or brand name but rarely part of a board slug.
_NAME_NOISE = {
    "inc", "llc", "ltd", "limited", "pvt", "private", "corp", "corporation", "co",
    "technologies", "technology", "labs", "systems", "solutions", "software",
    "services", "group", "india", "global", "hq", "the", "ai", "io", "app",
}

# Cities and regions that place an opening in India. Matched as whole words, so
# "Indiana" or "Indianapolis" don't count.
_INDIA_PLACES = (
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "navi mumbai",
    "gurugram", "gurgaon", "noida", "greater noida", "delhi", "new delhi", "ncr",
    "chennai", "kolkata", "ahmedabad", "jaipur", "kochi", "cochin", "coimbatore",
    "thiruvananthapuram", "trivandrum", "chandigarh", "mohali", "indore", "nagpur",
    "vadodara", "surat", "lucknow", "bhubaneswar", "mysuru", "mysore", "mangaluru",
    "mangalore", "visakhapatnam", "vizag", "goa", "karnataka", "telangana",
    "maharashtra", "tamil nadu", "haryana", "uttar pradesh", "kerala", "gujarat",
    "west bengal",
)
_INDIA_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in _INDIA_PLACES) + r")\b", re.IGNORECASE)
_INDIA_COUNTRY_CODES = {"in", "ind", "india"}
_REMOTE_RE = re.compile(r"\b(remote|anywhere|work from home|wfh)\b", re.IGNORECASE)


# --- candidates and slugs ---------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    name: str
    extra_slugs: tuple[str, ...] = ()


def parse_candidates(text: str) -> list[Candidate]:
    """Read candidates.txt: one company per line, optional ``| slug,slug`` extras.

    Blank lines and ``#`` comments are skipped. A name listed twice is kept once.
    """
    seen: set[str] = set()
    out: list[Candidate] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, extras = line.partition("|")
        name = name.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        slugs = tuple(s.strip().lower() for s in extras.split(",") if s.strip())
        out.append(Candidate(name=name, extra_slugs=slugs))
    return out


def _words(name: str) -> list[str]:
    cleaned = name.lower().replace("&", " and ").replace("+", " plus ")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return cleaned.split()


def slug_variants(name: str, extra_slugs: Iterable[str] = (), *, limit: int = 5) -> list[str]:
    """Likely board slugs for a company, most likely first.

    "Physics Wallah" -> physicswallah, physics-wallah; "Druva Inc" -> druvainc,
    druva-inc, druva. Explicit extras from candidates.txt come first.
    """
    words = _words(name)
    core = [w for w in words if w not in _NAME_NOISE] or words
    ordered = [
        *extra_slugs,
        "".join(words),
        "-".join(words),
        "".join(core),
        "-".join(core),
    ]
    out: list[str] = []
    for slug in ordered:
        slug = slug.strip().lower()
        if slug and slug not in out:
            out.append(slug)
    return out[:limit]


def name_matches(candidate: str, board_company: Optional[str]) -> Optional[bool]:
    """Whether a board's reported company name is the candidate we were looking for.

    None when the ATS doesn't report a name. Otherwise True when the significant
    words of one name are contained in the other ("Postman" vs "Postman Inc.").
    """
    if not board_company:
        return None
    a = {w for w in _words(candidate) if w not in _NAME_NOISE} or set(_words(candidate))
    b = {w for w in _words(board_company) if w not in _NAME_NOISE} or set(_words(board_company))
    if not a or not b:
        return False
    return a <= b or b <= a or "".join(sorted(a)) == "".join(sorted(b))


# --- reading board payloads --------------------------------------------------


def is_india_location(text: Optional[str]) -> bool:
    return bool(text and _INDIA_RE.search(text))


@dataclass
class Opening:
    title: str
    locations: list[str]
    india: bool
    remote: bool
    url: Optional[str] = None


def _greenhouse_openings(payload: dict[str, Any]) -> list[Opening]:
    out = []
    for job in payload.get("jobs") or []:
        loc = ((job.get("location") or {}).get("name") or "").strip()
        out.append(
            Opening(
                title=job.get("title") or "",
                locations=[loc] if loc else [],
                india=is_india_location(loc),
                remote=bool(_REMOTE_RE.search(loc)),
                url=job.get("absolute_url"),
            )
        )
    return out


def _lever_openings(payload: list[dict[str, Any]]) -> list[Opening]:
    out = []
    for job in payload or []:
        cats = job.get("categories") or {}
        locs = [l for l in (cats.get("allLocations") or [cats.get("location")]) if l]
        country = (job.get("country") or "").strip().lower()
        india = country in _INDIA_COUNTRY_CODES or any(is_india_location(l) for l in locs)
        remote = (job.get("workplaceType") or "").lower() == "remote" or any(_REMOTE_RE.search(l) for l in locs)
        out.append(Opening(title=job.get("text") or "", locations=locs, india=india, remote=remote, url=job.get("hostedUrl")))
    return out


def _ashby_openings(payload: dict[str, Any]) -> list[Opening]:
    out = []
    for job in payload.get("jobs") or []:
        if job.get("isListed") is False:
            continue
        places = [job, *(job.get("secondaryLocations") or [])]
        locs = [p.get("location") for p in places if p.get("location")]
        countries = {
            ((p.get("address") or {}).get("postalAddress") or {}).get("addressCountry", "").strip().lower()
            for p in places
        }
        india = bool(countries & _INDIA_COUNTRY_CODES) or any(is_india_location(l) for l in locs)
        remote = bool(job.get("isRemote")) or (job.get("workplaceType") or "").lower() == "remote"
        out.append(Opening(title=job.get("title") or "", locations=locs, india=india, remote=remote, url=job.get("jobUrl")))
    return out


def extract_openings(ats: str, payload: Any) -> list[Opening]:
    if ats == "greenhouse":
        return _greenhouse_openings(payload if isinstance(payload, dict) else {})
    if ats == "lever":
        return _lever_openings(payload if isinstance(payload, list) else [])
    if ats == "ashby":
        return _ashby_openings(payload if isinstance(payload, dict) else {})
    raise ValueError(f"unknown ATS: {ats}")


_INVISIBLE_RE = re.compile(r"[​-‏‪-‮⁠-⁤﻿]")


def board_company_name(ats: str, payload: Any) -> Optional[str]:
    """The company name the board itself reports (Greenhouse only).

    Boards sometimes carry invisible direction marks or zero-width spaces in the
    name; they are stripped so names compare, sort and display cleanly.
    """
    if ats == "greenhouse" and isinstance(payload, dict):
        for job in payload.get("jobs") or []:
            name = _INVISIBLE_RE.sub("", job.get("company_name") or "").strip()
            if name:
                return name
    return None


@dataclass
class BoardEntry:
    """One verified board, as written to registry.json."""

    name: str
    ats: str
    board_token: str
    india_openings: int
    total_openings: int
    remote_openings: int
    sample_locations: list[str]
    sample_job_url: Optional[str]
    board_company_name: Optional[str]
    name_verified: Optional[bool]
    probed_at: str
    domain: Optional[str] = None
    source: str = "candidates"  # candidates (name guess) | crawl (discovered slug)


def summarize_board(candidate: Candidate, ats: str, slug: str, payload: Any, probed_at: str) -> BoardEntry:
    openings = extract_openings(ats, payload)
    india = [o for o in openings if o.india]
    samples: list[str] = []
    for o in india:
        for loc in o.locations:
            if is_india_location(loc) and loc not in samples:
                samples.append(loc)
    company = board_company_name(ats, payload)
    return BoardEntry(
        name=candidate.name,
        ats=ats,
        board_token=slug,
        india_openings=len(india),
        total_openings=len(openings),
        remote_openings=sum(1 for o in openings if o.remote),
        sample_locations=samples[:5],
        sample_job_url=(india[0].url if india else (openings[0].url if openings else None)),
        board_company_name=company,
        name_verified=name_matches(candidate.name, company),
        probed_at=probed_at,
    )


# --- probing -----------------------------------------------------------------


class HostRateLimiter:
    """At most ``rate`` requests per second to each host."""

    def __init__(self, rate: float):
        self.interval = 1.0 / rate if rate > 0 else 0.0
        self._next: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            start = max(now, self._next.get(host, now))
            self._next[host] = start + self.interval
        if start > now:
            await asyncio.sleep(start - now)


class ResponseCache:
    """Probe responses on disk, so an interrupted run resumes without re-asking.

    Misses (404) are cached too: they are most of the traffic.
    """

    def __init__(self, root: Optional[Path]):
        self.root = root

    def _path(self, ats: str, slug: str) -> Optional[Path]:
        if self.root is None:
            return None
        safe = re.sub(r"[^a-z0-9._-]", "_", slug.lower())
        return self.root / ats / f"{safe}.json"

    def get(self, ats: str, slug: str) -> Optional[dict[str, Any]]:
        path = self._path(ats, slug)
        if path and path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        return None

    def put(self, ats: str, slug: str, status: int, body: Any) -> None:
        path = self._path(ats, slug)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": status, "body": body}), encoding="utf-8")


async def fetch_board(
    client: httpx.AsyncClient,
    ats: str,
    slug: str,
    *,
    limiter: HostRateLimiter,
    cache: ResponseCache,
    retries: int = 3,
) -> tuple[int, Any]:
    """(status, parsed JSON or None) for one board. Retries 429/5xx with backoff."""
    cached = cache.get(ats, slug)
    if cached is not None:
        return cached["status"], cached["body"]

    url = BOARD_URLS[ats].format(slug=slug)
    host = httpx.URL(url).host
    delay = 2.0
    for attempt in range(retries + 1):
        await limiter.wait(host)
        try:
            resp = await client.get(url)
        except httpx.HTTPError:
            if attempt == retries:
                return 0, None  # network trouble: not cached, so a re-run retries it
            await asyncio.sleep(delay)
            delay *= 2
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == retries:
                return resp.status_code, None
            retry_after = resp.headers.get("retry-after")
            await asyncio.sleep(float(retry_after) if retry_after and retry_after.isdigit() else delay)
            delay *= 2
            continue
        body = None
        if resp.status_code == 200:
            try:
                body = resp.json()
            except ValueError:
                body = None
        cache.put(ats, slug, resp.status_code, body)
        return resp.status_code, body
    return 0, None


@dataclass
class ProbeResult:
    candidate: Candidate
    entry: Optional[BoardEntry] = None  # first board with an India opening
    boards_without_india: list[BoardEntry] = field(default_factory=list)
    requests: int = 0
    errors: int = 0


async def probe_candidate(
    client: httpx.AsyncClient,
    candidate: Candidate,
    *,
    limiter: HostRateLimiter,
    cache: ResponseCache,
    now: Optional[str] = None,
) -> ProbeResult:
    """Try each slug variant on each ATS; stop at the first board with an India opening.

    On one ATS, the first variant that answers 200 is that company's board there,
    so later variants on that ATS are skipped.
    """
    probed_at = now or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    result = ProbeResult(candidate=candidate)
    slugs = slug_variants(candidate.name, candidate.extra_slugs)
    for ats in ATS_VENDORS:
        for slug in slugs:
            status, body = await fetch_board(client, ats, slug, limiter=limiter, cache=cache)
            result.requests += 1
            if status == 0 or status == 429 or status >= 500:
                result.errors += 1
                continue
            if status != 200 or body is None:
                continue
            entry = summarize_board(candidate, ats, slug, body, probed_at)
            if entry.name_verified is False:
                # A different company owns this slug: keep looking.
                continue
            if entry.india_openings > 0:
                result.entry = entry
                return result
            result.boards_without_india.append(entry)
            break
    return result


def parse_boards(text: str) -> list[tuple[str, str]]:
    """Read discovered-boards.txt: ``ats:slug`` per line, ``#`` comments skipped."""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        ats, _, slug = line.partition(":")
        key = (ats.strip().lower(), slug.strip().lower())
        if key[0] in ATS_VENDORS and key[1] and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def name_from_slug(slug: str) -> str:
    """'hevodata' -> 'Hevodata', 'acme-robotics' -> 'Acme Robotics'. A fallback only."""
    return " ".join(part.capitalize() for part in re.split(r"[-_.]+", slug) if part) or slug


async def probe_board(
    client: httpx.AsyncClient,
    ats: str,
    slug: str,
    *,
    limiter: HostRateLimiter,
    cache: ResponseCache,
    now: Optional[str] = None,
) -> ProbeResult:
    """Probe one known board slug. The name comes from the board when it reports one."""
    probed_at = now or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    status, body = await fetch_board(client, ats, slug, limiter=limiter, cache=cache)
    result = ProbeResult(candidate=Candidate(name_from_slug(slug)), requests=1)
    if status == 0 or status == 429 or status >= 500:
        result.errors = 1
        return result
    if status != 200 or body is None:
        return result
    name = board_company_name(ats, body) or name_from_slug(slug)
    entry = summarize_board(Candidate(name), ats, slug, body, probed_at)
    entry.name_verified = None  # nothing to check the name against
    entry.source = "crawl"
    result.candidate = Candidate(name)
    if entry.india_openings > 0:
        result.entry = entry
    else:
        result.boards_without_india.append(entry)
    return result


def merge_entries(*groups: Iterable[BoardEntry]) -> list[BoardEntry]:
    """One entry per (ats, board), earlier groups winning (name guesses have better names)."""
    out: dict[tuple[str, str], BoardEntry] = {}
    for group in groups:
        for e in group:
            out.setdefault((e.ats, e.board_token), e)
    return list(out.values())


def sort_registry(entries: Iterable[BoardEntry]) -> list[BoardEntry]:
    return sorted(entries, key=lambda e: (-e.india_openings, e.name.lower()))


def entries_to_json(entries: Iterable[BoardEntry]) -> str:
    return json.dumps([asdict(e) for e in entries], indent=2, ensure_ascii=False) + "\n"


# --- loading into the database ----------------------------------------------


def load_registry(db: Session, entries: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Upsert registry entries into ``companies``.

    Matched first by (ats_vendor, ats_board_token), then by a company with the same
    name and no board yet (so the fixture companies pick up their board), else created.
    """
    stats = {"created": 0, "updated": 0}
    for e in entries:
        checked = _parse_time(e.get("probed_at"))
        company = (
            db.query(Company)
            .filter(Company.ats_vendor == e["ats"], Company.ats_board_token == e["board_token"])
            .first()
        )
        if company is None:
            company = (
                db.query(Company)
                .filter(Company.name.ilike(e["name"]), Company.ats_vendor.is_(None))
                .first()
            )
        if company is None:
            company = Company(name=e["name"], domain=e.get("domain"))
            db.add(company)
            stats["created"] += 1
        else:
            stats["updated"] += 1
        company.ats_vendor = e["ats"]
        company.ats_board_token = e["board_token"]
        company.ats_checked_at = checked
        if e.get("domain") and not company.domain:
            company.domain = e["domain"]
    db.commit()
    return stats


def _parse_time(value: Optional[str]) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
