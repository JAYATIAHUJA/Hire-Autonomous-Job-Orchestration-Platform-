"""Build Evidence Index rows from analysed contributions.

Pure and in-memory, like ``builder``: contributions in, row dicts out. Each row
ties one skill to one citeable GitHub URL — the commit or pull request that shows
it, plus one roll-up row per (skill, repository). Bulk changes (initial commits,
vendored imports) are not evidence of anyone's skill and are left out.
"""

import re
from collections import Counter
from typing import Any, Iterable

from ..analysis.contribution import Contribution
from ..analysis.skills import load_rules, skills_for_contribution
from ..time_utils import to_naive_utc

MAX_CONTRIBUTIONS_PER_SKILL = 25
_GITHUB_URL = re.compile(r"^https://github\.com/[\w.\-]+/[\w.\-]+(?:/(?:commit/[0-9a-f]{7,40}|pull/\d+))?$")


def skill_key(name: str) -> str:
    """Lookup key: case and punctuation folded, but "C", "C#" and "C++" stay distinct."""
    return re.sub(r"[^a-z0-9+#]", "", name.lower())


def build_evidence(contributions: Iterable[Contribution]) -> list[dict[str, Any]]:
    rules = load_rules()
    per_skill: dict[str, list[dict[str, Any]]] = {}
    for c in contributions:
        if c.bulk or c.weight <= 0 or not _GITHUB_URL.match(c.url or ""):
            continue
        for skill, (weight, lines, reasons) in skills_for_contribution(c, rules).items():
            if weight <= 0:
                continue
            per_skill.setdefault(skill, []).append({
                "skill": skill,
                "skill_key": skill_key(skill),
                "repo": c.repo,
                "url": c.url,
                "kind": "pr" if c.kind == "pr" else "commit",
                "weight": round(weight, 3),
                "date": to_naive_utc(c.date),
                "summary": _summary(c, lines, reasons),
                "is_private": c.private,
            })

    rows: list[dict[str, Any]] = []
    for skill, items in per_skill.items():
        items.sort(key=lambda r: (-r["weight"], r["url"]))
        kept = items[:MAX_CONTRIBUTIONS_PER_SKILL]
        rows.extend(kept)
        rows.extend(_repo_rollups(skill, kept))
    return rows


def _repo_rollups(skill: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_repo: dict[str, list[dict[str, Any]]] = {}
    for r in items:
        by_repo.setdefault(r["repo"], []).append(r)
    out = []
    for repo, rs in by_repo.items():
        n = len(rs)
        dates = [r["date"] for r in rs if r["date"]]
        out.append({
            "skill": skill,
            "skill_key": skill_key(skill),
            "repo": repo,
            "url": f"https://github.com/{repo}",
            "kind": "repo",
            "weight": round(sum(r["weight"] for r in rs), 3),
            "date": max(dates) if dates else None,
            "summary": f"{n} analysed contribution{'' if n == 1 else 's'} in {repo} show {skill}.",
            "is_private": any(r["is_private"] for r in rs),
        })
    return out


def _summary(c: Contribution, lines: int, reasons: Counter) -> str:
    what = "Merged pull request" if c.kind == "pr" else "Commit"
    signals = []
    for (kind, key), n in reasons.most_common(2):
        if kind == "import":
            signals.append(f"imports {key}")
        elif kind == "dependency":
            signals.append(f"adds dependency {key}")
        elif kind == "language":
            signals.append(f"{n} {key} file{'' if n == 1 else 's'}")
        elif kind == "path":
            signals.append(f"changes {key}")
        elif kind == "category":
            signals.append(f"{n} {key} file{'' if n == 1 else 's'}")
    detail = f" ({', '.join(signals)}; {lines} lines)" if signals else ""
    return f"{what} ({c.type}): {c.title}{detail}"
