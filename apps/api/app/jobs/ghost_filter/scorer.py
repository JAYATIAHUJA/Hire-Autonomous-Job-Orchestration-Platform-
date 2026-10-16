"""Algorithmic Ghost Job Classification and Probability Scoring Model.

Calculates the probability P(Legitimate) that a job opening represents genuine hiring intent:
    P(Legitimate) = 1 / (1 + e^-(beta_0 - beta_age*X_age - beta_repost*X_repost - beta_news*X_news + beta_salary*X_salary + beta_quality*X_quality))

Maps the resulting probability to a standardized Ghost Score (0-999):
    0-399:   Low Risk / High Legitimacy (Verified active hiring intent)
    400-699: Moderate Risk (Communication / minor posting age gaps)
    700-999: High Risk / Ghost Job (High probability of phantom / compliance posting)

Execution Rule:
    Listings in the 700-999 range are automatically purged from the candidate feed.
"""

import math
from dataclasses import dataclass
from typing import Optional

from .features import ExtractedJobFeatures, extract_features


# Calibrated logistic model coefficients
DEFAULT_COEFFICIENTS = {
    "beta_0": 0.85,          # Baseline prior for a standard new job listing
    "beta_age": 2.75,        # Penalty for prolonged posting age (> 60 days)
    "beta_repost": 2.20,     # Penalty for repeated reposting without modifications
    "beta_news": 3.40,       # Severe penalty for corporate mass layoffs / WARN notices
    "beta_salary": 1.60,     # Boost for explicit compensation transparency
    "beta_quality": 2.10,    # Boost for technical specificity vs vague buzzwords
}


@dataclass
class GhostScoreResult:
    ghost_score: int
    risk_band: str  # "Low" | "Moderate" | "High"
    legitimacy_probability: float
    is_ghost: bool  # True if ghost_score >= 700
    features: ExtractedJobFeatures

    def to_dict(self) -> dict:
        return {
            "ghost_score": self.ghost_score,
            "risk_band": self.risk_band,
            "legitimacy_probability": self.legitimacy_probability,
            "is_ghost": self.is_ghost,
            "posting_age_days": self.features.raw_age_days,
            "repost_count": self.features.raw_repost_count,
        }


def calculate_legitimacy_probability(
    features: ExtractedJobFeatures,
    coefficients: Optional[dict[str, float]] = None,
) -> float:
    """Calculate P(Legitimate) using the calibrated logistic equation."""
    c = coefficients or DEFAULT_COEFFICIENTS
    z = (
        c["beta_0"]
        - (c["beta_age"] * features.x_age)
        - (c["beta_repost"] * features.x_repost)
        - (c["beta_news"] * features.x_news)
        + (c["beta_salary"] * features.x_salary)
        + (c["beta_quality"] * features.x_quality)
    )

    # Sigmoid function with overflow safety
    if z < -20.0:
        return 0.0001
    if z > 20.0:
        return 0.9999
    return 1.0 / (1.0 + math.exp(-z))


def score_job(
    *,
    posting_age_days: int,
    repost_count: int,
    raw_description: str,
    salary_range: Optional[str] = None,
    company_name: str = "",
    company_domain: Optional[str] = None,
    external_layoff_flag: Optional[bool] = None,
    coefficients: Optional[dict[str, float]] = None,
) -> GhostScoreResult:
    """End-to-end feature extraction and Ghost Scoring."""
    features = extract_features(
        posting_age_days=posting_age_days,
        repost_count=repost_count,
        raw_description=raw_description,
        salary_range=salary_range,
        company_name=company_name,
        company_domain=company_domain,
        external_layoff_flag=external_layoff_flag,
    )

    p_legitimate = calculate_legitimacy_probability(features, coefficients)

    # Standardized Ghost Score (0 - 999): higher means higher ghost risk
    ghost_score = int(round((1.0 - p_legitimate) * 999))
    ghost_score = max(0, min(999, ghost_score))

    # Risk band mapping
    if ghost_score < 400:
        risk_band = "Low"
    elif ghost_score < 700:
        risk_band = "Moderate"
    else:
        risk_band = "High"

    is_ghost = ghost_score >= 700

    return GhostScoreResult(
        ghost_score=ghost_score,
        risk_band=risk_band,
        legitimacy_probability=round(p_legitimate, 3),
        is_ghost=is_ghost,
        features=features,
    )
