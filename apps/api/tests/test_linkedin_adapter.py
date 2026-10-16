import pytest
from app.jobs.ingestion.linkedin_adapter import parse_linkedin_job_cards


SAMPLE_LINKEDIN_HTML = """
<ul class="jobs-search__results-list">
    <li>
        <div class="base-card">
            <a class="base-card__full-link" href="https://in.linkedin.com/jobs/view/backend-developer-at-cred-4426311357?position=1"></a>
            <h3 class="base-search-card__title">Backend Engineer - Core Payments</h3>
            <h4 class="base-search-card__subtitle">
                <a href="https://in.linkedin.com/company/cred">CRED</a>
            </h4>
            <span class="job-search-card__location">Bengaluru, Karnataka, India</span>
            <time datetime="2026-09-15">3 days ago</time>
        </div>
    </li>
    <li>
        <div class="base-card">
            <a class="base-card__full-link" href="https://in.linkedin.com/jobs/view/sde-1-at-zepto-4426311358?position=2"></a>
            <h3 class="base-search-card__title">Software Development Engineer I</h3>
            <h4 class="base-search-card__subtitle">
                <a href="https://in.linkedin.com/company/zepto">Zepto</a>
            </h4>
            <span class="job-search-card__location">Hyderabad, Telangana, India</span>
            <time datetime="2026-09-17">1 day ago</time>
        </div>
    </li>
</ul>
"""


def test_parse_linkedin_job_cards():
    cards = parse_linkedin_job_cards(SAMPLE_LINKEDIN_HTML)
    assert len(cards) == 2

    c1 = cards[0]
    assert c1["title"] == "Backend Engineer - Core Payments"
    assert c1["company_name"] == "CRED"
    assert "Bengaluru" in c1["location"]
    assert c1["source_id"].startswith("job_cred_backend-engineer-core-payments_")

    c2 = cards[1]
    assert c2["title"] == "Software Development Engineer I"
    assert c2["company_name"] == "Zepto"
    assert "Hyderabad" in c2["location"]
