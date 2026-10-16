"""Global Job Description (JD) hashing and content normalization.

Up to 80% of applicants apply to overlapping corporate roles. Normalizing and
hashing raw JDs allows the platform to check a global cache before executing
heavy NLP extraction, ghost classification, or downstream LLM embeddings for
Student A's RAG engine, slashing downstream token spend by up to 80%.
"""

import hashlib
import re
from typing import Optional


def normalize_job_description(text: Optional[str]) -> str:
    """Normalize job description text by stripping formatting noise and redundant whitespace."""
    if not text:
        return ""
    # Normalize unicode whitespace and line endings
    clean_lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    ]
    cleaned = "\n".join(clean_lines)
    # Collapse multiple blank lines
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


def compute_description_hash(text: Optional[str], algorithm: str = "md5") -> str:
    """Calculate deterministic hex digest of normalized job description.
    
    Defaults to 32-character hex MD5 as required by the shared data contract.
    """
    normalized = normalize_job_description(text).lower()
    if algorithm == "sha256":
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()
