import pytest
from app.jobs.ghost_filter.scorer import score_job


def test_high_legitimacy_job_scores_low_risk():
    result = score_job(
        posting_age_days=6,
        repost_count=0,
        raw_description=(
            "Join our core team building high-scale payments with Go, PostgreSQL, Redis, and Docker. "
            "Write microservices and automated tests."
        ),
        salary_range="₹14,00,000 - ₹20,00,000 INR",
        company_name="CredTech",
        company_domain="credtech.io",
        external_layoff_flag=False,
    )

    assert result.ghost_score < 400
    assert result.risk_band == "Low"
    assert result.legitimacy_probability >= 0.60
    assert result.is_ghost is False


def test_ghost_job_scores_high_risk_and_purges():
    # Listing > 60 days old, repeatedly reposted, vague buzzwords, layoff flag
    result = score_job(
        posting_age_days=85,
        repost_count=4,
        raw_description=(
            "Looking for an urgent rockstar ninja to wear multiple hats in dynamic fast-paced environment. "
            "Continuous talent pipeline drive. Hustle and synergies."
        ),
        salary_range=None,
        company_name="Apex Global Edtech",
        company_domain="apex-edtech-layoff.com",
        external_layoff_flag=True,
    )

    assert result.ghost_score >= 700
    assert result.risk_band == "High"
    assert result.legitimacy_probability < 0.30
    assert result.is_ghost is True


def test_moderate_risk_job():
    result = score_job(
        posting_age_days=35,
        repost_count=1,
        raw_description="Java developer with Spring Boot for enterprise consulting. Basic database knowledge.",
        salary_range=None,
        company_name="InnoSoft",
        company_domain="innosoft-sample.in",
        external_layoff_flag=False,
    )

    assert 300 <= result.ghost_score < 700
    assert result.risk_band in {"Low", "Moderate"}
