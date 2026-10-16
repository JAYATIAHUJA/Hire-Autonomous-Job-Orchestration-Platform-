import pytest
from app.jobs.ingestion.hasher import compute_description_hash, normalize_job_description


def test_normalize_job_description_cleans_noise():
    raw = "  Backend Engineer \r\n\r\n\t with Python  and   FastAPI.\n\n\n\nApply now.  "
    normalized = normalize_job_description(raw)
    assert "\r" not in normalized
    assert "   " not in normalized
    assert normalized == "Backend Engineer\n\nwith Python and FastAPI.\n\nApply now."


def test_compute_description_hash_deterministic():
    text1 = "Backend Software Engineer with FastAPI and Docker."
    text2 = "  backend software engineer with fastapi and docker.  \n"

    # Both should evaluate to the identical hash due to normalization
    hash1 = compute_description_hash(text1)
    hash2 = compute_description_hash(text2)

    assert len(hash1) == 32
    assert hash1 == hash2

    # Different text yields distinct hash
    diff_hash = compute_description_hash("Frontend React Developer")
    assert hash1 != diff_hash
