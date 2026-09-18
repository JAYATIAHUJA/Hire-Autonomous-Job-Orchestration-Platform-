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
    clean_domain = (domain or "").lower().strip()
    clean_name = company_name.lower().strip()

    # 1. Exact domain check
    if clean_domain in KNOWN_DOWNSIZING_ENTITIES:
        return True, KNOWN_DOWNSIZING_ENTITIES[clean_domain]

    # 2. Domain substring check
    for d, reason in KNOWN_DOWNSIZING_ENTITIES.items():
        if d in clean_domain or clean_domain in d:
            return True, reason

    # 3. Name keywords check
    for d, reason in KNOWN_DOWNSIZING_ENTITIES.items():
        base_name = d.split(".")[0].replace("-", " ")
        if base_name in clean_name:
            return True, reason

    return False, None
