"""Read real openings from employers' public job boards (Greenhouse, Lever, Ashby).

The companies come from the ATS registry (``app/jobs/ats_registry.py``): boards a probe
has seen answer with at least one India-located opening. Each discovery round reads the
boards fetched longest ago, keeps tech roles that are in India or remote, and turns
each into a pipeline item with its source and the employer's own posting URL.

Only the documented, unauthenticated board APIs are used; nothing is scraped.
"""

from __future__ import annotations

import asyncio
import datetime
import html
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from ...config import settings
from ..ats_registry import is_india_location

USER_AGENT = "Hire/1.0 (job discovery; +https://github.com/JAYATIAHUJA)"

FEED_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
}

# Roles our users (software engineers and students) apply to. Matched on the title.
_TECH_RE = re.compile(
    r"\b(engineer|engineering|developer|sde|swe|software|programmer|data|machine learning|ml|ai|"
    r"devops|sre|reliability|qa|test|automation|security|frontend|front-end|backend|back-end|"
    r"full[- ]?stack|mobile|android|ios|cloud|platform|infrastructure|architect|scientist|"
    r"analytics|analyst|intern|graduate|trainee|technical|tech lead|web|embedded|firmware)\b",
    re.I,
)
_REMOTE_RE = re.compile(r"\b(remote|anywhere|work from home|wfh)\b", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class BoardResult:
    ok: bool
    items: list[dict[str, Any]] = field(default_factory=list)
    seen_ids: set[str] = field(default_factory=set)
    error: Optional[str] = None


def fix_mojibake(text: str) -> str:
    """Undo UTF-8 read as Latin-1 ("Weâ€™re" -> "We’re"), which some feeds send."""
    if not any(marker in text for marker in ("â€", "Ã", "Â")):
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        try:
            return text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text


def plain_text(raw: Optional[str]) -> str:
    """HTML (sometimes HTML-escaped HTML, as Greenhouse sends it) to readable text."""
    text = fix_mojibake(html.unescape(html.unescape(raw or "")))
    text = re.sub(r"<\s*(br|/p|/li|/h\d)\s*/?>", "\n", text, flags=re.I)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def experience_from_title(title: str) -> str:
    t = title.lower()
    if re.search(r"\bintern(ship)?\b|\btrainee\b|\bapprentice\b", t):
        return "Internship"
    if re.search(r"\b(senior|sr\.?|staff|principal|lead|manager|head|director|architect|sde[- ]?iii|sde[- ]?3|iii)\b", t):
        return "Senior (5+ yrs)"
    if re.search(r"\b(sde[- ]?ii|sde[- ]?2|ii|mid)\b", t):
        return "Mid-Level (2-5 yrs)"
    if re.search(r"\b(junior|jr\.?|associate|graduate|fresher|entry|new grad|sde[- ]?i|sde[- ]?1|i)\b", t):
        return "Entry-Level (0-2 yrs)"
    return "Not stated"


def _age_days(when: Optional[datetime.datetime]) -> int:
    if when is None:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    return max(0, (now - when).days)


def _parse_iso(value: Any) -> Optional[datetime.datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


def _from_ms(value: Any) -> Optional[datetime.datetime]:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.datetime.fromtimestamp(value / 1000, tz=datetime.timezone.utc)
    return None


_OPEN_TO_INDIA = re.compile(r"\b(worldwide|anywhere|global|india|asia|apac|emea|remote)\b", re.I)
_COUNTRY_ONLY = re.compile(r"\b(usa|us|united states|canada|uk|united kingdom|europe|eu|germany|latam|americas?|amer|"
                           r"brazil|mexico|australia|new zealand)\b", re.I)


def open_to_india(location: Any) -> bool:
    """Empty, "Worldwide", "Anywhere", "India", "APAC": yes. "USA", "Remote - Canada": no."""
    text = str(location or "").strip()
    if not text:
        return True
    if re.search(r"\b(india|asia|apac|worldwide|anywhere|global)\b", text, re.I):
        return True
    return not _COUNTRY_ONLY.search(text) and bool(_OPEN_TO_INDIA.search(text))


def remote_open_to_india(locations: list[str], countries: set[str] = frozenset()) -> bool:
    """A remote role an applicant in India can take: no country, or India, and a location
    such as "Remote", "Worldwide" or "APAC" rather than "Zurich, Switzerland"."""
    named = {c for c in countries if c}
    if named and not named & {"in", "ind", "india"}:
        return False
    return not locations or any(open_to_india(l) for l in locations)


def is_tech_title(title: str) -> bool:
    return bool(title and _TECH_RE.search(title))


def _keep(title: str, locations: list[str], remote: bool, india: bool, countries: set[str] = frozenset()) -> bool:
    """Tech roles based in India, or remote roles open to someone in India."""
    if not (title and _TECH_RE.search(title)):
        return False
    return india or (remote and remote_open_to_india(locations, countries))


def _item(*, ats: str, board: str, job_id: str, company: str, domain: Optional[str], title: str,
          locations: list[str], remote: bool, url: Optional[str], posted: Optional[datetime.datetime],
          description: str, salary: Optional[str]) -> dict[str, Any]:
    location = ", ".join(dict.fromkeys(l for l in locations if l)) or ("Remote" if remote else "India")
    return {
        "source_id": f"{ats}_{board}_{job_id}",
        "source": ats,
        "apply_url": url,
        "posted_at": posted,
        "is_remote": remote,
        "company_name": company,
        "company_domain": domain,
        "external_layoff_flag": False,
        "title": title.strip(),
        "location": location[:200],
        "salary_range": salary,
        "posting_age_days": _age_days(posted),
        "repost_count": 0,
        "experience_level": experience_from_title(title),
        "primary_skills": [],
        "raw_description": description[:20000] or title,
    }


def parse_board(ats: str, board: str, company: str, domain: Optional[str], payload: Any) -> BoardResult:
    """Turn one board's JSON into pipeline items (tech roles in India or remote only)."""
    result = BoardResult(ok=True)
    if ats == "greenhouse":
        for job in (payload or {}).get("jobs") or []:
            jid = str(job.get("id") or "")
            loc = ((job.get("location") or {}).get("name") or "").strip()
            result.seen_ids.add(f"{ats}_{board}_{jid}")
            remote = bool(_REMOTE_RE.search(loc))
            title = job.get("title") or ""
            if not _keep(title, [loc], remote, is_india_location(loc)):
                continue
            posted = _parse_iso(job.get("first_published")) or _parse_iso(job.get("updated_at"))
            result.items.append(_item(
                ats=ats, board=board, job_id=jid, company=company, domain=domain, title=title, locations=[loc],
                remote=remote, url=job.get("absolute_url"), posted=posted,
                description=plain_text(job.get("content")), salary=None,
            ))
    elif ats == "lever":
        for job in payload or []:
            jid = str(job.get("id") or "")
            cats = job.get("categories") or {}
            locs = [l for l in (cats.get("allLocations") or [cats.get("location")]) if l]
            result.seen_ids.add(f"{ats}_{board}_{jid}")
            country = (job.get("country") or "").strip().lower()
            india = country in {"in", "ind", "india"} or any(is_india_location(l) for l in locs)
            remote = (job.get("workplaceType") or "").lower() == "remote" or any(_REMOTE_RE.search(l) for l in locs)
            title = job.get("text") or ""
            if not _keep(title, locs, remote, india):
                continue
            parts = [job.get("descriptionPlain") or ""]
            for block in job.get("lists") or []:
                parts.append(f"{block.get('text', '')}\n{plain_text(block.get('content'))}")
            parts.append(job.get("additionalPlain") or "")
            sal = job.get("salaryRange") or {}
            salary = (
                f"{sal.get('currency', '')} {sal['min']:,} - {sal['max']:,} / {sal.get('interval', 'year')}".strip()
                if isinstance(sal.get("min"), (int, float)) and isinstance(sal.get("max"), (int, float)) else None
            )
            result.items.append(_item(
                ats=ats, board=board, job_id=jid, company=company, domain=domain, title=title, locations=locs,
                remote=remote, url=job.get("hostedUrl"), posted=_from_ms(job.get("createdAt")),
                description="\n\n".join(p for p in parts if p).strip(), salary=salary,
            ))
    elif ats == "ashby":
        for job in (payload or {}).get("jobs") or []:
            if job.get("isListed") is False:
                continue
            jid = str(job.get("id") or "")
            result.seen_ids.add(f"{ats}_{board}_{jid}")
            places = [job, *(job.get("secondaryLocations") or [])]
            locs = [p.get("location") for p in places if p.get("location")]
            countries = {
                ((p.get("address") or {}).get("postalAddress") or {}).get("addressCountry", "").strip().lower()
                for p in places
            }
            india = bool(countries & {"in", "ind", "india"}) or any(is_india_location(l) for l in locs)
            remote = bool(job.get("isRemote")) or (job.get("workplaceType") or "").lower() == "remote"
            title = job.get("title") or ""
            if not _keep(title, locs, remote, india, countries):
                continue
            comp = (job.get("compensation") or {}).get("compensationTierSummary")
            result.items.append(_item(
                ats=ats, board=board, job_id=jid, company=company, domain=domain, title=title, locations=locs,
                remote=remote, url=job.get("jobUrl") or job.get("applyUrl"), posted=_parse_iso(job.get("publishedAt")),
                description=job.get("descriptionPlain") or plain_text(job.get("descriptionHtml")), salary=comp or None,
            ))
    else:
        return BoardResult(ok=False, error=f"unknown ATS {ats}")
    return result


async def fetch_board(client: httpx.AsyncClient, ats: str, board: str, company: str,
                      domain: Optional[str]) -> BoardResult:
    url = FEED_URLS[ats].format(slug=board)
    try:
        resp = await client.get(url, timeout=60)
    except httpx.HTTPError as exc:
        return BoardResult(ok=False, error=f"{type(exc).__name__}")
    if resp.status_code != 200:
        return BoardResult(ok=False, error=f"HTTP {resp.status_code}")
    try:
        return parse_board(ats, board, company, domain, resp.json())
    except ValueError:
        return BoardResult(ok=False, error="bad JSON")


async def fetch_boards(boards: list[tuple[str, str, str, Optional[str]]]) -> list[BoardResult]:
    """Fetch several boards, a few at a time. ``boards`` = (ats, token, company, domain)."""
    sem = asyncio.Semaphore(max(1, settings.ats_fetch_concurrency))
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        async def one(b: tuple[str, str, str, Optional[str]]) -> BoardResult:
            async with sem:
                return await fetch_board(client, *b)

        return await asyncio.gather(*(one(b) for b in boards))
