import pytest
from app.jobs.ghost_filter.features import (
    compute_description_specificity,
    compute_salary_transparency,
    extract_features,
)
from app.jobs.ghost_filter.layoff_tracker import check_layoff_signal


def test_posting_age_scaling():
    # Fresh posting (<= 14 days)
    fresh = extract_features(posting_age_days=7, repost_count=0, raw_description="Python developer")
    assert fresh.x_age <= 0.10

    # Moderate age (30 days)
    moderate = extract_features(posting_age_days=30, repost_count=0, raw_description="Python developer")
    assert 0.30 <= moderate.x_age <= 0.40

    # Old posting (> 60 days) receives steep penalty
    old = extract_features(posting_age_days=90, repost_count=0, raw_description="Python developer")
    assert old.x_age >= 0.80


def test_repost_frequency_scaling():
    zero = extract_features(posting_age_days=10, repost_count=0, raw_description="Dev")
    assert zero.x_repost == 0.0

    two = extract_features(posting_age_days=10, repost_count=2, raw_description="Dev")
    assert round(two.x_repost, 2) == 0.67

    four = extract_features(posting_age_days=10, repost_count=4, raw_description="Dev")
    assert four.x_repost == 1.0


def test_salary_transparency():
    # Explicit numerical compensation
    assert compute_salary_transparency("₹12 LPA - ₹18 LPA", "Backend dev") == 1.0
    assert compute_salary_transparency("$120,000 - $160,000 USD", "Full stack") == 1.0

    # Embedded in description text
    assert compute_salary_transparency(None, "Great team. CTC: 15,00,000 per annum") > 0.8

    # Vague generic placeholders
    assert compute_salary_transparency("Best in industry", "Software engineer") == 0.1
    assert compute_salary_transparency("Competitive as per market rate", "Developer") == 0.1

    # Absent
    assert compute_salary_transparency(None, "Regular job description without any numbers.") == 0.0


def test_description_specificity_and_buzzword_penalties():
    # Concrete technical listing
    tech_desc = (
        "We are looking for a Backend Engineer to build microservices using Python, FastAPI, "
        "PostgreSQL, Redis, Kafka, and Docker. Responsibilities include writing automated unit tests."
    )
    score_tech, skills = compute_description_specificity(tech_desc)
    assert score_tech >= 0.70
    assert {"fastapi", "postgresql", "redis", "docker"} <= set(skills)

    # Vague buzzword-heavy ghost listing
    buzz_desc = (
        "Seeking a rockstar ninja developer who can wear multiple hats in a fast-paced startup! "
        "Must be a self-starter with a passion for synergies and willingness to hustle on various ad-hoc tasks."
    )
    score_buzz, _ = compute_description_specificity(buzz_desc)
    assert score_buzz < 0.35


def test_layoff_signal_detection():
    is_layoff, detail = check_layoff_signal("Apex Edtech Corp", "apex-edtech-layoff.com")
    assert is_layoff is True
    assert "edtech" in detail.lower()

    is_clean, _ = check_layoff_signal("Swiggy Technologies", "swiggy.com")
    assert is_clean is False
