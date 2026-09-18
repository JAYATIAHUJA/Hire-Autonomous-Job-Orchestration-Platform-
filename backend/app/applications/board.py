"""Kanban stage vocabulary and the transition rules that guard it.

The board a candidate sees has three columns — Applied, Interview Scheduled and
Rejected. A card enters at ``applied`` the moment a swipe right records consent,
and is moved on either by the background IMAP reader (recruiter replies) or by
the candidate dragging it themselves.

Automated moves are deliberately more restricted than manual ones: a mail parser
may only push a card forward (or to rejected), never resurrect a closed card.
"""

STAGE_APPLIED = "applied"
STAGE_INTERVIEW = "interview_scheduled"
STAGE_REJECTED = "rejected"
STAGE_SKIPPED = "skipped"

# Columns rendered on the board, left to right. ``skipped`` is tracked so a
# swiped-away job never returns to the deck, but it is not a board column.
BOARD_STAGES: tuple[str, ...] = (STAGE_APPLIED, STAGE_INTERVIEW, STAGE_REJECTED)
ALL_STAGES: tuple[str, ...] = BOARD_STAGES + (STAGE_SKIPPED,)

STAGE_LABELS: dict[str, str] = {
    STAGE_APPLIED: "Applied",
    STAGE_INTERVIEW: "Interview Scheduled",
    STAGE_REJECTED: "Rejected",
    STAGE_SKIPPED: "Skipped",
}

# Moves the candidate may make by hand on the board.
MANUAL_TRANSITIONS: dict[str, set[str]] = {
    STAGE_APPLIED: {STAGE_INTERVIEW, STAGE_REJECTED},
    STAGE_INTERVIEW: {STAGE_REJECTED, STAGE_APPLIED},
    STAGE_REJECTED: {STAGE_APPLIED, STAGE_INTERVIEW},
    STAGE_SKIPPED: {STAGE_APPLIED},
}

# Moves the background IMAP reader may make on the candidate's behalf.
AUTOMATED_TRANSITIONS: dict[str, set[str]] = {
    STAGE_APPLIED: {STAGE_INTERVIEW, STAGE_REJECTED},
    STAGE_INTERVIEW: {STAGE_REJECTED},
    STAGE_REJECTED: set(),
    STAGE_SKIPPED: set(),
}


def is_valid_stage(stage: str) -> bool:
    return stage in ALL_STAGES


def can_transition(from_stage: str, to_stage: str, *, automated: bool = False) -> bool:
    """Whether a card may move between two stages for the given actor."""
    table = AUTOMATED_TRANSITIONS if automated else MANUAL_TRANSITIONS
    return to_stage in table.get(from_stage, set())


def label_for(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage)
