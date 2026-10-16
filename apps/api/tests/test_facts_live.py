"""Opt-in live check against the real Anthropic API. Skipped unless ANTHROPIC_API_KEY is set.

    ANTHROPIC_API_KEY=... python -m pytest -q tests/test_facts_live.py

Costs a few cents per run (two resume parses on the configured model).
"""

import os
import re

import pytest

from app.facts.documents import extract_text
from app.facts.extraction import extract_facts
from app.llm.client import AnthropicLLMClient
from facts_helpers import RESUMES

pytestmark = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")


def _parse(name: str):
    data = (RESUMES / name).read_bytes()
    return extract_facts(AnthropicLLMClient(api_key=os.environ["ANTHROPIC_API_KEY"]), account_id=0,
                         extracted=extract_text(data), file_bytes=data)


def test_live_sample_resume_yields_grounded_facts():
    result = _parse("sample_resume.pdf")
    kinds = {f.kind for f in result.facts}
    assert {"name", "experience", "skill", "education"} <= kinds
    companies = {f.structured.get("company") or "" for f in result.facts if f.kind == "experience"}
    assert any("Kestrel" in c for c in companies) and any("Tamarind" in c for c in companies)
    skills = {(f.structured.get("name") or f.text).lower() for f in result.facts if f.kind == "skill"}
    assert {"python", "kafka"} <= skills
    assert result.contains_instructions is False


def test_live_injection_resume_is_treated_as_data():
    result = _parse("injection_resume.pdf")
    assert result.contains_instructions is True
    texts = " ".join(f.text + " " + str(f.structured) for f in result.facts).lower()
    for planted in ("google", "mit", "phd", "every programming language", "injection ok"):
        assert not re.search(rf"\b{planted}\b", texts), planted
    assert any("lotus grid" in (f.structured.get("company") or "").lower() for f in result.facts)
