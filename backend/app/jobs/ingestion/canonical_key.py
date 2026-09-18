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
    """Generates a canonical, URL-safe, deduplicated job key.
    
    Format: `<company_slug>_<title_slug>` (e.g. `swiggy_backend-engineer-5d2f8a`).
    """
    comp_slug = cap_slug(slugify(company) or "company", COMPANY_MAX)
    role_slug = cap_slug(slugify(title) or "role", TITLE_MAX)

    if not role_slug or role_slug == "role":
        if raw_id:
            role_slug = slugify(raw_id) or "posting"
        else:
            role_slug = "job"

    # Add disambiguation hash based on company + title + raw_id
    seed = f"{company.strip().lower()}::{title.strip().lower()}::{raw_id or ''}"
    disambig = hashlib.md5(seed.encode("utf-8")).hexdigest()[:6]

    return f"job_{comp_slug}_{role_slug}_{disambig}"
