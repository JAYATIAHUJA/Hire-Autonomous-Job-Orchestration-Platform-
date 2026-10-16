"""Shared helpers for the fact-vault tests."""

from pathlib import Path

from app.facts.extraction import STRUCTURED_FIELDS

RESUMES = Path(__file__).parent / "fixtures" / "resumes"


def fact(kind: str, text: str, inferred: bool = False, evidence: str = "", **structured) -> dict:
    """One fact exactly as the model's tool call would return it."""
    return {
        "kind": kind,
        "text": text,
        "inferred": inferred,
        "evidence": evidence or text,
        "structured": {name: structured.get(name) for name in STRUCTURED_FIELDS},
    }


SAMPLE_FACTS = [
    fact("name", "Priya Venkataraman"),
    fact("contact_email", "priya.v@example.com"),
    fact("location", "Pune, India"),
    fact("experience", "Senior Backend Engineer at Kestrel Logistics", company="Kestrel Logistics",
         title="Senior Backend Engineer", start_date="2023-01", end_date="present"),
    fact("achievement", "Cut p95 latency of shipment tracking from 900 ms to 180 ms",
         company="Kestrel Logistics", title="Senior Backend Engineer"),
    fact("experience", "Backend Engineer at Tamarind Pay", company="Tamarind Pay", title="Backend Engineer",
         start_date="2020-07", end_date="2022-12"),
    fact("achievement", "Built the UPI refund reconciliation API", company="Tamarind Pay", title="Backend Engineer"),
    fact("education", "B.Tech in Computer Science, Coastal Institute of Technology",
         institution="Coastal Institute of Technology", degree="B.Tech in Computer Science",
         start_date="2016", end_date="2020"),
    fact("skill", "Python", name="Python"),
    fact("skill", "Kafka", name="Kafka"),
    fact("language", "English (C1)", name="English", level="C1"),
    fact("work_authorization", "India: citizen", country="India"),
    fact("skill", "Distributed systems", inferred=True, name="Distributed systems"),
]


def tool_output(facts, contains_instructions=False) -> dict:
    return {"facts": facts, "contains_instructions": contains_instructions}
