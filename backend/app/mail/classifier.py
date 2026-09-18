"""Reads a recruiter reply and decides which column its card belongs in.

Recruiter mail is formulaic, so weighted phrase matching is enough and, unlike an
LLM call, it costs nothing and is deterministic under test. Both directions are
scored and the stronger one wins, because the two vocabularies overlap: an
interview mail may open with "Unfortunately that slot is taken", and a rejection
almost always mentions the interview the candidate is not getting.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from ..applications.board import STAGE_INTERVIEW, STAGE_REJECTED

# (pattern, weight). Weight 2 = decisive on its own, 1 = supporting hint.
REJECTION_SIGNALS: list[tuple[str, int]] = [
    (r"regret to inform", 3),
    (r"(decided|chosen|opted) to (move|go) forward with (other|another)", 3),
    (r"will not be (moving|proceeding) forward", 3),
    (r"not (be )?(moving|proceeding) forward with your (application|candidature|profile)", 3),
    (r"(were|was) not selected", 3),
    (r"no longer (under consideration|being considered)", 3),
    (r"(position|role|vacancy) has (since )?been filled", 3),
    (r"pursu(e|ing) other candidates", 3),
    (r"not a (good |strong )?(fit|match) (for|at) this time", 2),
    (r"keep your (resume|cv|profile) on file", 2),
    (r"wish you (all )?the best (in|with) your (job )?search", 2),
    (r"unfortunately", 1),
    (r"\bdeclin(e|ed|ing)\b", 1),
]

INTERVIEW_SIGNALS: list[tuple[str, int]] = [
    (r"(schedule|set up|arrange|book)(ing)? (an?|the|your) (interview|call|chat|screen)", 3),
    (r"invit(e|ing|ation) (you )?(to|for) (an?|the) (interview|call|conversation|discussion)", 3),
    (r"interview (invitation|invite|scheduled|confirmation)", 3),
    (r"(technical|first|second|final|hr) (round|interview)", 3),
    (r"(you have been |you.?re )?shortlisted", 3),
    (r"(move|moving|proceed|proceeding) (you )?(forward|ahead) (to|with) the (next|interview)", 3),
    (r"next round", 2),
    (r"(share|confirm|let us know) your availability", 2),
    (r"available for a (call|chat|discussion)", 2),
    (r"(calendar|meeting) (invite|link)", 2),
    (r"(coding|screening|assessment) (round|test|link|call)", 2),
    (r"(hiring manager|recruiter) would like to (speak|meet|connect)", 2),
    (r"looking forward to speaking", 1),
]


@dataclass
class ReplyClassification:
    """What a single recruiter mail means for the card it belongs to."""

    stage: Optional[str]  # None when the mail is not a decision either way
    confidence: float
    signals: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def is_decision(self) -> bool:
        return self.stage is not None


def _score(text: str, table: list[tuple[str, int]]) -> tuple[int, list[str]]:
    total = 0
    hits: list[str] = []
    for pattern, weight in table:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            total += weight
            hits.append(match.group(0).strip().lower())
    return total, hits


def classify_reply(subject: str = "", body: str = "") -> ReplyClassification:
    """Classify a recruiter reply as a rejection, an interview invite, or neither."""
    # The subject line carries the verdict more often than the body, so it counts twice.
    text = " \n ".join([subject or "", subject or "", body or ""])

    reject_score, reject_hits = _score(text, REJECTION_SIGNALS)
    interview_score, interview_hits = _score(text, INTERVIEW_SIGNALS)

    if reject_score == 0 and interview_score == 0:
        return ReplyClassification(stage=None, confidence=0.0, summary="No hiring decision detected.")

    if reject_score == interview_score:
        # A genuine tie is ambiguous; leave the card where it is for a human to read.
        return ReplyClassification(
            stage=None,
            confidence=0.0,
            signals=reject_hits + interview_hits,
            summary="Reply matched rejection and interview language equally - left for manual review.",
        )

    if reject_score > interview_score:
        stage, score, hits, wording = STAGE_REJECTED, reject_score, reject_hits, "Rejection"
    else:
        stage, score, hits, wording = STAGE_INTERVIEW, interview_score, interview_hits, "Interview"

    confidence = round(score / (reject_score + interview_score), 2)
    return ReplyClassification(
        stage=stage,
        confidence=confidence,
        signals=hits,
        summary=f"{wording} detected from: " + ", ".join(hits[:3]) + ".",
    )
