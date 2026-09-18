"""Quantitative feature extraction pipeline for Ghost Job scoring.

Extracts the five primary red-flag signals from raw job listings:
1. X_age: Posting age in days (penalizing postings > 60 days).
2. X_repost: Repost frequency count without description change.
3. X_quality: Description specificity evaluated via TF-IDF and keyword density.
4. X_salary: Salary transparency score (numerical range vs vague placeholders).
5. X_news: External downsizing/layoff signal (WARN tracker / news flag).
"""

import math
import re
from dataclasses import dataclass
from typing import Optional

from .layoff_tracker import check_layoff_signal


# Tech framework and deliverable vocabulary
SPECIFIC_TECH_TOKENS = {
    "python", "fastapi", "django", "flask", "javascript", "typescript", "react", "next.js",
    "vue", "angular", "node.js", "express", "go", "golang", "rust", "java", "spring", "spring boot",
    "kotlin", "c++", "c#", "sql", "postgresql", "mysql", "mongodb", "redis", "kafka", "docker",
    "kubernetes", "aws", "gcp", "azure", "graphql", "rest", "grpc", "ci/cd", "git", "linux",
    "microservices", "unit tests", "jest", "pytest", "terraform", "html", "css", "tailwind"
}

# Generic corporate buzzwords indicative of passive resume harvesting or ghost postings
VAGUE_BUZZWORDS = {
    "rockstar", "ninja", "guru", "wizard", "wear multiple hats", "wear many hats",
    "dynamic environment", "fast-paced environment", "fast-paced startup", "synergies",
    "self-starter", "various ad-hoc", "wear multiple hats", "hustle", "high-octane",
    "continuous recruitment", "continuous pipeline", "future placement", "as per industry",
    "competitive compensation for the right candidate", "talent pool", "submit your cv"
}

# Regex to detect concrete numerical compensation
NUMERICAL_SALARY_REGEX = re.compile(
    r"(₹|\$|€|£|inr|usd|lpa|ctc|lakhs?|k\b|\d{1,3}(?:,\d{3})+|\d+\s*-\s*\d+)",
    re.IGNORECASE,
)

GENERIC_SALARY_PLACEHOLDERS = re.compile(
    r"\b(competitive|industry standards?|best in industry|market rate|as per industry|doe|negotiable)\b",
    re.IGNORECASE,
)


@dataclass
class ExtractedJobFeatures:
    raw_age_days: int
    raw_repost_count: int
    x_age: float
    x_repost: float
    x_quality: float
    x_salary: float
    x_news: float
    layoff_detail: Optional[str] = None
    detected_skills: list[str] = None

    def to_feature_vector(self) -> list[float]:
        """Returns standard vector [x_age, x_repost, x_news, x_salary, x_quality]."""
        return [self.x_age, self.x_repost, self.x_news, self.x_salary, self.x_quality]


def compute_salary_transparency(salary_range: Optional[str], raw_text: str) -> float:
    """Evaluate salary transparency (1.0 = clear numerical range, 0.0 = absent/vague)."""
    text_to_check = (salary_range or "") + " " + raw_text
    if not salary_range and not NUMERICAL_SALARY_REGEX.search(text_to_check):
        return 0.0

    if salary_range:
        if GENERIC_SALARY_PLACEHOLDERS.search(salary_range) and not re.search(r"\d", salary_range):
            return 0.1
        if NUMERICAL_SALARY_REGEX.search(salary_range):
            return 1.0

    # If salary range field wasn't set, check if raw description clearly mentions CTC / salary
    if re.search(r"(₹|\$|\bctc\b|\blpa\b|\blakhs?\b)\s*[:\-]?\s*[\d,]+", text_to_check, re.IGNORECASE):
        return 0.85

    return 0.0


def compute_description_specificity(text: str) -> tuple[float, list[str]]:
    """Calculate TF-IDF style description specificity and extract concrete skill tags.
    
    Returns:
        (specificity_score [0.0 - 1.0], list_of_detected_skills)
    """
    if not text:
        return 0.0, []

    lower = text.lower()
    words = re.findall(r"\b[a-z0-9_.\-+#]+\b", lower)
    total_words = len(words)

    # 1. Tech keywords match
    matched_skills = [skill for skill in SPECIFIC_TECH_TOKENS if re.search(rf"\b{re.escape(skill)}\b", lower)]
    tech_density = min(len(matched_skills) / 4.0, 1.0)

    if total_words < 5:
        return 0.1, sorted(matched_skills)

    # 2. Vague buzzwords penalty
    buzzword_hits = sum(1 for phrase in VAGUE_BUZZWORDS if phrase in lower)
    buzzword_penalty = min(buzzword_hits * 0.25, 0.75)

    # 3. Structural length factor (too short = vague, comprehensive = specific)
    length_factor = min(math.log10(max(total_words, 10)) / 2.5, 1.0)

    # 4. Composite specificity score
    specificity = (0.50 * tech_density) + (0.30 * length_factor) + (0.20 * (1.0 - buzzword_penalty))
    specificity = max(0.0, min(specificity - (buzzword_penalty * 0.4), 1.0))

    return round(specificity, 3), sorted(matched_skills)


def extract_features(
    *,
    posting_age_days: int,
    repost_count: int,
    raw_description: str,
    salary_range: Optional[str] = None,
    company_name: str = "",
    company_domain: Optional[str] = None,
    external_layoff_flag: Optional[bool] = None,
) -> ExtractedJobFeatures:
    """Extract quantitative features X_age, X_repost, X_quality, X_salary, X_news."""
    # 1. Posting Age (X_age): Normalized with steep exponential penalty above 60 days
    age = max(0, posting_age_days)
    if age <= 14:
        x_age = 0.10 * (age / 14.0)
    elif age <= 30:
        x_age = 0.10 + 0.25 * ((age - 14) / 16.0)
    elif age <= 60:
        x_age = 0.35 + 0.35 * ((age - 30) / 30.0)
    else:
        # > 60 days receives severe risk penalty
        x_age = min(0.70 + 0.30 * ((age - 60) / 60.0), 1.0)

    # 2. Repost Frequency (X_repost): Reposted without description updates
    reposts = max(0, repost_count)
    x_repost = min(reposts / 3.0, 1.0)

    # 3. Description Specificity (X_quality)
    x_quality, skills = compute_description_specificity(raw_description)

    # 4. Salary Transparency (X_salary)
    x_salary = compute_salary_transparency(salary_range, raw_description)

    # 5. External Layoff / Downsizing Signal (X_news)
    layoff_flag, layoff_detail = check_layoff_signal(company_name, company_domain)
    if external_layoff_flag is not None:
        layoff_flag = layoff_flag or external_layoff_flag
        if external_layoff_flag and not layoff_detail:
            layoff_detail = "Company flagged with active downsizing/WARN notice"

    x_news = 1.0 if layoff_flag else 0.0

    return ExtractedJobFeatures(
        raw_age_days=age,
        raw_repost_count=reposts,
        x_age=round(x_age, 3),
        x_repost=round(x_repost, 3),
        x_quality=round(x_quality, 3),
        x_salary=round(x_salary, 3),
        x_news=round(x_news, 3),
        layoff_detail=layoff_detail,
        detected_skills=skills,
    )
