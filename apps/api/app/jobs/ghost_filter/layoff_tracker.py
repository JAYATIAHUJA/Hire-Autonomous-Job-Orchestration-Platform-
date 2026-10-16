"""External Downsizing & Freeze Signal Detector.

Cross-references company domain names and corporate entities against layoff databases,
WARN notice filings, and news signals. A job posting from a company currently undergoing
a mass layoff or hiring freeze is flagged with a high ghost probability.
"""

import re
from typing import Optional

# Registry of company domains and keywords associated with active layoff / freeze signals
KNOWN_DOWNSIZING_ENTITIES: dict[str, str] = {
    "apex-edtech-layoff.com": "Mass layoff reported: 40% workforce reduction in edtech sector",
    "byjus.com": "Severe restructuring and active hiring freeze",
    "unacademy.com": "Workforce rationalization program in progress",
    "talentpool-harvest.io": "Passive talent harvesting firm without active headcount budget",
    "meta.com": "Historical WARN filing audit flag",
    "better.com": "Operational contraction notice",
}

DOWNSIZING_KEYWORDS = re.compile(
    r"\b(layoff|downsizing|workforce reduction|hiring freeze|restructuring|job cuts|headcount reduction)\b",
    re.IGNORECASE,
)


def check_layoff_signal(company_name: str, domain: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Check if a company is associated with external downsizing or hiring freeze signals.
    
    Returns:
        (is_flagged, reason_or_detail)
    """
    # Only the registrable domain is trusted. An empty domain must never match: in
    # Python "" is a substring of every string, which once flagged every listing that
    # arrived without a domain. Company names are not matched at all, because short
    # names ("meta", "better") are substrings of unrelated employers.
    clean_domain = (domain or "").lower().strip().rstrip(".")
    if clean_domain.startswith("www."):
        clean_domain = clean_domain[4:]
    if not clean_domain:
        return False, None

    if clean_domain in KNOWN_DOWNSIZING_ENTITIES:
        return True, KNOWN_DOWNSIZING_ENTITIES[clean_domain]

    # Subdomains of a flagged domain (careers.byjus.com) count; look-alikes (notbyjus.com) do not.
    for d, reason in KNOWN_DOWNSIZING_ENTITIES.items():
        if clean_domain.endswith("." + d):
            return True, reason

    return False, None
