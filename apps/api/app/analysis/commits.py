import re

CONVENTIONAL = re.compile(r"^(\w+)(?:\([^)]*\))?!?:\s")
PREFIX_TYPES = {
    "feat": "feature", "feature": "feature",
    "fix": "fix", "bugfix": "fix", "hotfix": "fix",
    "test": "test", "tests": "test",
    "refactor": "refactor", "perf": "refactor",
    "docs": "docs", "doc": "docs",
    "ci": "ci/infra", "build": "ci/infra",
    "chore": "chore", "style": "chore", "revert": "chore",
}
FIX_WORDS = re.compile(r"\b(fix(e[sd])?|bug(s|fix)?|resolve[sd]?|patch(ed)?|hotfix|crash(es)?|typo)\b", re.I)
REFACTOR_WORDS = re.compile(
    r"\b(refactor\w*|clean\s?up|cleanup|rename[sd]?|restructur\w*|reorganiz\w*|simplif\w*|extract(ed)?|move[sd]?)\b",
    re.I,
)
FEATURE_WORDS = re.compile(r"\b(add(s|ed)?|implement\w*|creat\w*|support\w*|introduc\w*|build|new|enabl\w*|initial)\b", re.I)

BULK_FILES = 100
BULK_LINES = 5000


def classify_commit(message: str, categories: list[str], additions: int, deletions: int) -> str:
    """Deterministic work-type label from the message, falling back to what the change touched."""
    first_line = (message or "").strip().splitlines()[0] if (message or "").strip() else ""

    if m := CONVENTIONAL.match(first_line):
        if kind := PREFIX_TYPES.get(m.group(1).lower()):
            return kind

    relevant = {c for c in categories if c not in {"generated", "lockfile"}}
    if relevant:
        if relevant == {"test"}:
            return "test"
        if relevant == {"docs"}:
            return "docs"
        if relevant <= {"ci", "infra"}:
            return "ci/infra"
        if relevant <= {"manifest", "config", "other"}:
            return "chore"

    if FIX_WORDS.search(first_line):
        return "fix"
    if REFACTOR_WORDS.search(first_line):
        return "refactor"
    if FEATURE_WORDS.search(first_line):
        return "feature"
    # New features mostly add code; heavy rewriting of existing lines reads as refactoring.
    if additions + deletions > 0 and deletions >= 0.6 * additions:
        return "refactor"
    return "feature"


def is_bulk(files_touched: int, meaningful_lines: int) -> bool:
    """Vendored code, generated scaffolds and big initial imports say little about the author's own work."""
    return files_touched > BULK_FILES or meaningful_lines > BULK_LINES
