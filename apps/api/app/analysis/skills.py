import json
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .contribution import Contribution

RULES_PATH = Path(__file__).resolve().parent.parent / "skill_rules.json"
CATEGORY_LABELS = {"test": "test", "ci": "CI pipeline", "infra": "infrastructure", "docs": "documentation"}
# A dependency added without code using it yet is a weak signal on its own.
DEPENDENCY_ONLY_SHARE = 0.25


@lru_cache
def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _matches(value: str, key: str) -> bool:
    v, k = value.lower(), key.lower()
    return v == k or (v.startswith(k) and v[len(k)] in "-/.:_")


@dataclass
class SkillEvidence:
    name: str
    contributions: list = field(default_factory=list)
    weight: float = 0.0
    lines: int = 0
    projects: set = field(default_factory=set)
    external_prs: int = 0
    months: set = field(default_factory=set)
    feature_contributions: int = 0
    first_active: Optional[str] = None
    last_active: Optional[str] = None
    reasons: Counter = field(default_factory=Counter)  # (kind, key) -> count

    def add(self, c: Contribution, weight: float, lines: int) -> None:
        self.contributions.append(c)
        self.weight += weight
        self.lines += lines
        self.projects.add(c.repo)
        if c.external and c.kind == "pr":
            self.external_prs += 1
        if c.type == "feature" and not c.bulk and lines > 0:
            self.feature_contributions += 1
        if c.date:
            self.months.add(c.date[:7])
            if self.first_active is None or c.date < self.first_active:
                self.first_active = c.date
            if self.last_active is None or c.date > self.last_active:
                self.last_active = c.date

    def detected_via(self, limit: int = 4) -> list[str]:
        def s(n: int) -> str:
            return "" if n == 1 else "s"

        out = []
        for (kind, key), n in self.reasons.most_common(limit):
            if kind == "language":
                out.append(f"Changed {n} {key} file{s(n)}")
            elif kind == "import":
                out.append(f"Imports {key} in {n} changed file{s(n)}")
            elif kind == "dependency":
                out.append(f"Added dependency {key}" + (f" ({n}×)" if n > 1 else ""))
            elif kind == "category":
                out.append(f"Changed {n} {CATEGORY_LABELS.get(key, key)} file{s(n)}")
            elif kind == "path":
                out.append(f"Changed {n} {key} file{s(n)}")
        return out


def skills_for_contribution(c: Contribution, rules: dict) -> dict[str, tuple[float, int, Counter]]:
    """skill -> (weight, lines attributed, reasons). Credit is limited to the files that show the skill."""
    found: dict[str, tuple[float, int, Counter]] = {}
    total = sum(f.lines for f in c.files) or 1

    def credit(lines: int) -> float:
        return c.weight * min(lines / total, 1.0)

    for language, lines in c.language_lines.items():
        files = sum(1 for f in c.files if f.language == language and f.category in {"source", "test"} and f.lines)
        found[language] = (credit(lines), lines, Counter({("language", language): files}))

    for skill, rule in rules.items():
        reasons: Counter = Counter()
        matched_files = set()
        for f in c.files:
            for key in rule.get("imports", []):
                if any(_matches(imp, key) for imp in f.imports):
                    reasons[("import", key)] += 1
                    matched_files.add(f)
            if f.category in rule.get("categories", []):
                reasons[("category", f.category)] += 1
                matched_files.add(f)
            for key in rule.get("paths", []):
                if key in f.path:
                    reasons[("path", key)] += 1
                    matched_files.add(f)
        dependency_hit = False
        for dep in c.dependencies_added:
            if any(_matches(dep, key) for key in rule.get("dependencies", [])):
                reasons[("dependency", dep)] += 1
                dependency_hit = True
        if not reasons:
            continue

        lines = sum(f.lines for f in matched_files)
        weight = max(credit(lines), c.weight * DEPENDENCY_ONLY_SHARE if dependency_hit else 0.0)
        if skill in found:  # e.g. "SQL" from .sql files and from database imports
            old_weight, old_lines, old_reasons = found[skill]
            found[skill] = (max(old_weight, weight), max(old_lines, lines), old_reasons + reasons)
        else:
            found[skill] = (weight, lines, reasons)
    return found


def infer_skills(contributions: list[Contribution]) -> dict[str, SkillEvidence]:
    rules = load_rules()
    skills: dict[str, SkillEvidence] = {}
    for c in contributions:
        for name, (weight, lines, reasons) in skills_for_contribution(c, rules).items():
            evidence = skills.setdefault(name, SkillEvidence(name=name))
            evidence.add(c, weight, lines)
            evidence.reasons.update(reasons)
    return skills
