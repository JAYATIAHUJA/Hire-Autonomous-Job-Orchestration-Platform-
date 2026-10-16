"""Live LinkedIn Public Job Search Adapter (adapted from ai-job-search).

Accesses LinkedIn's public 'jobs-guest' endpoints with zero credentials,
no authentication, and zero API keys required. Fetches live postings
across India and global markets (Bengaluru, Hyderabad, Pune, Remote, etc.).
"""

import html
import re
from typing import Any, Optional
import httpx
from bs4 import BeautifulSoup

from .canonical_key import generate_canonical_job_id

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def search_linkedin_jobs(
    keywords: str = "software engineer",
    location: str = "Bengaluru, Karnataka, India",
    limit: int = 10,
    page: int = 1,
) -> list[dict[str, Any]]:
    """Search LinkedIn's public guest job API for live openings."""
    params = {
        "keywords": keywords,
        "location": location,
        "start": str((page - 1) * 10),
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(SEARCH_URL, params=params, headers=headers)
            if resp.status_code != 200:
                return []
            return parse_linkedin_job_cards(resp.text)[:limit]
    except Exception:
        return []


def parse_linkedin_job_cards(html_content: str) -> list[dict[str, Any]]:
    """Extract job listings from LinkedIn guest search response."""
    soup = BeautifulSoup(html_content, "html.parser")
    cards = []

    for li in soup.find_all("li"):
        title_tag = li.find("h3", class_="base-search-card__title")
        comp_tag = li.find("h4", class_="base-search-card__subtitle")
        loc_tag = li.find("span", class_="job-search-card__location")
        link_tag = li.find("a", class_="base-card__full-link")
        time_tag = li.find("time")

        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        company = comp_tag.get_text(strip=True) if comp_tag else "Unknown Company"
        loc = loc_tag.get_text(strip=True) if loc_tag else "India (Hybrid/Remote)"
        url = link_tag.get("href", "") if link_tag else ""
        date_str = time_tag.get_text(strip=True) if time_tag else "Recent"

        # Extract LinkedIn numeric ID from link
        match = re.search(r"(\d{8,})", url)
        raw_id = match.group(1) if match else None

        canonical_id = generate_canonical_job_id(company, title, raw_id)

        cards.append({
            "source_id": canonical_id,
            "company_name": company,
            "company_domain": f"{re.sub(r'[^a-z0-9]', '', company.lower())}.com",
            "external_layoff_flag": False,
            "title": title,
            "location": loc,
            "salary_range": None,  # LinkedIn guest cards rarely expose compensation upfront
            "posting_age_days": 5,  # Recent search query
            "repost_count": 0,
            "experience_level": "Entry-Level / Mid",
            "primary_skills": [],
            "raw_description": f"{title} position at {company} located in {loc}. Date posted: {date_str}. Apply via LinkedIn: {url}",
            "job_url": url,
        })

    return cards


async def fetch_linkedin_job_detail(job_id_or_urn: str) -> Optional[str]:
    """Fetch full text description for a LinkedIn job posting."""
    # Extract numeric id
    match = re.search(r"(\d{8,})", job_id_or_urn)
    if not match:
        return None
    numeric_id = match.group(1)

    url = f"{DETAIL_URL}/{numeric_id}"
    headers = {"User-Agent": USER_AGENT}

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                desc_div = soup.find("div", class_="show-more-less-html__markup")
                if desc_div:
                    return desc_div.get_text(separator="\n", strip=True)
                return soup.get_text(separator="\n", strip=True)
    except Exception:
        pass
    return None
