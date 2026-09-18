import pytest
from app.jobs.ingestion.canonical_key import cap_slug, generate_canonical_job_id, slugify


def test_slugify_clean():
    assert slugify("Acme Systems, Inc.") == "acme-systems-inc"
    assert slugify("Software Engineer (Backend / Python)") == "software-engineer-backend-python"
    assert slugify("Deloitte // SOC Analyst") == "deloitte-soc-analyst"


def test_generate_canonical_job_id_deterministic():
    id1 = generate_canonical_job_id("Swiggy", "Backend Software Engineer", "blr_swig_001")
    id2 = generate_canonical_job_id("Swiggy", "Backend Software Engineer", "blr_swig_001")
    assert id1 == id2
    assert id1.startswith("job_swiggy_backend-software-engineer_")

    # Minor casing/whitespace variance produces same canonical id
    id3 = generate_canonical_job_id("  swiggy  ", "backend software engineer", "blr_swig_001")
    assert id1 == id3


def test_cap_slug_with_hash():
    short = cap_slug("short-slug", 20)
    assert short == "short-slug"

    long_str = "a" * 100
    capped = cap_slug(long_str, 30)
    assert len(capped) <= 30
    assert "-" in capped
