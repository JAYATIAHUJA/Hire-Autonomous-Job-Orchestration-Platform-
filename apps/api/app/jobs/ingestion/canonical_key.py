"""Deterministic canonical deduplication key generation.

Adapted from the ai-job-search pattern (MadsLorentzen/ai-job-search):
Produces a clean, deterministic, collision-resistant slug identifier across
diverse job boards and scraping sources, preventing duplicate postings
when titles are slightly formatted or truncated differently across portals.
"""

import hashlib
import re
import unicodedata
from typing import Optional

_NON_SLUG = re.compile(r"[^a-z0-9]+")
COMPANY_MAX = 40
TITLE_MAX = 60
HASH_LEN = 8


def slugify(text: Optional[str]) -> str:
    """Normalize text into lowercase ASCII slug."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return _NON_SLUG.sub("-", ascii_only.lower()).strip("-")


def cap_slug(slug: str, limit: int) -> str:
    """Cap slug length without losing uniqueness by appending a deterministic hash."""
    if len(slug) <= limit:
        return slug
    digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:HASH_LEN]
    head = slug[: limit - HASH_LEN - 1].rstrip("-")
    return f"{head}-{digest}"


def generate_canonical_job_id(
    company: str,
    title: str,
    raw_id: Optional[str] = None,
) -> str:
    """A URL-safe id for one posting *on one source*.

    Format: `job_<company_slug>_<title_slug>_<hash>`. The hash covers the source's
    own posting id, so two different openings with the same title stay separate.
    That also means it differs across portals - use :func:`cross_portal_key` to
    find the same job listed on two boards.
    """
    comp_slug = cap_slug(slugify(company) or "company", COMPANY_MAX)
    role_slug = cap_slug(slugify(title) or "role", TITLE_MAX)

    if not role_slug or role_slug == "role":
        if raw_id:
            role_slug = slugify(raw_id) or "posting"
        else:
            role_slug = "job"

    seed = f"{company.strip().lower()}::{title.strip().lower()}::{raw_id or ''}"
    disambig = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6]

    return f"job_{comp_slug}_{role_slug}_{disambig}"


# Words that differ between portals for the same employer ("Swiggy" vs
# "Swiggy Technologies Pvt Ltd").
_COMPANY_NOISE = {
    "inc", "llc", "ltd", "limited", "pvt", "private", "corp", "corporation", "co",
    "company", "technologies", "technology", "tech", "labs", "systems", "solutions",
    "software", "services", "group", "engineering", "india", "global", "the",
}
_TITLE_NOISE = {"the", "a", "an", "role", "position", "opening", "job", "hiring", "urgent"}
_CITY_ALIASES = {
    "bangalore": "bengaluru", "bengaluru": "bengaluru", "gurgaon": "gurugram",
    "gurugram": "gurugram", "bombay": "mumbai", "new-delhi": "delhi", "delhi": "delhi",
    "madras": "chennai", "calcutta": "kolkata", "noida": "noida",
}


def _tokens(text: Optional[str], noise: set[str]) -> list[str]:
    return [t for t in slugify(text).split("-") if t and t not in noise]


def normalize_location(location: Optional[str]) -> str:
    """'Bengaluru, Karnataka, India', 'Bangalore' and 'Bengaluru (Hybrid)' -> 'bengaluru'."""
    slug = slugify(location)
    if not slug:
        return ""
    if "remote" in slug.split("-"):
        return "remote"
    first = slugify((location or "").split(",")[0].split("(")[0])
    return _CITY_ALIASES.get(first, first)


def cross_portal_key(company: str, title: str, location: Optional[str] = None) -> str:
    """The same job listed on several boards gets the same key.

    Built only from what every portal shows - employer, title and city - never from
    a portal's own posting id (which is why the old key could not dedupe anything).
    """
    comp = "-".join(_tokens(company, _COMPANY_NOISE)) or slugify(company)
    role = "-".join(_tokens(title, _TITLE_NOISE)) or slugify(title)
    seed = f"{comp}::{role}::{normalize_location(location)}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()
