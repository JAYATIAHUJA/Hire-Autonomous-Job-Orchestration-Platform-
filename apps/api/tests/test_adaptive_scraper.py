import os
import tempfile
import pytest
from app.jobs.ingestion.adaptive_scraper import AdaptiveScraper, FingerprintDatabase


@pytest.fixture
def temp_fp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = FingerprintDatabase(db_path=db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)


def test_adaptive_scraper_initial_and_self_healing(temp_fp_db):
    scraper = AdaptiveScraper(fp_db=temp_fp_db)

    # Initial HTML layout
    initial_html = """
    <html>
        <body>
            <div class="job-container">
                <h1 class="job-title-original" data-testid="job-title">Staff Backend Engineer</h1>
                <div class="job-description">We build distributed systems with Go and Kafka.</div>
            </div>
        </body>
    </html>
    """

    # 1. Initial extraction using working selector
    title, conf, was_healed = scraper.extract_with_self_healing(
        initial_html,
        source="acme-careers",
        target_field="title",
        fallback_selector="h1.job-title-original",
    )
    assert title == "Staff Backend Engineer"
    assert conf == 1.0
    assert was_healed is False

    # 2. Site updates DOM classes (Selector Rot): class renamed from 'job-title-original' to 'role-header-v2'
    mutated_html = """
    <html>
        <body>
            <div class="job-container">
                <h1 class="role-header-v2" data-testid="job-title">Staff Backend Engineer</h1>
                <div class="job-description">We build distributed systems with Go and Kafka.</div>
            </div>
        </body>
    </html>
    """

    # Primary selector 'h1.job-title-original' no longer matches!
    # Auto-match should calculate similarity against stored fingerprint and self-heal
    healed_title, healed_conf, was_healed = scraper.extract_with_self_healing(
        mutated_html,
        source="acme-careers",
        target_field="title",
        fallback_selector="h1.job-title-original",
    )

    assert healed_title == "Staff Backend Engineer"
    assert healed_conf >= 0.70
    assert was_healed is True
