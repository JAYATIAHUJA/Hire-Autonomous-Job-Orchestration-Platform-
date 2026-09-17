from collections import Counter

from ..analysis.contribution import Contribution

WORK_TYPES = ["feature", "fix", "refactor", "test", "ci/infra", "docs", "chore"]


def timeline(dates: list[str]) -> list[dict]:
    months = Counter(d[:7] for d in dates if d)
    return [{"month": m, "commits": n} for m, n in sorted(months.items())]


def work_mix(contributions: list[Contribution]) -> list[dict]:
    counts: Counter = Counter()
    lines: Counter = Counter()
    for c in contributions:
        counts[c.type] += 1
        lines[c.type] += c.meaningful_lines
    return [{"type": t, "count": counts[t], "lines": lines[t]} for t in WORK_TYPES if counts[t]]
