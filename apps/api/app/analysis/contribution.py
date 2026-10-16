import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from .commits import classify_commit, is_bulk
from .files import IGNORED_CATEGORIES, MEANINGFUL_CATEGORIES, classify_file
from .imports import extract_added_dependencies, extract_added_imports

TYPE_MULTIPLIER = {
    "feature": 1.0, "fix": 0.8, "refactor": 0.8, "test": 0.7, "ci/infra": 0.6, "docs": 0.4, "chore": 0.3,
}
EXTERNAL_PR_MULTIPLIER = 2.0
BULK_MULTIPLIER = 0.1


@dataclass(frozen=True)
class FileChange:
    path: str  # lowercased
    category: str
    language: Optional[str]
    lines: int  # additions + deletions
    imports: frozenset


@dataclass
class Contribution:
    kind: str  # "commit" | "pr"
    repo: str
    external: bool
    url: str
    title: str
    date: Optional[str]
    type: str = "feature"
    meaningful_additions: int = 0
    meaningful_deletions: int = 0
    other_lines: int = 0
    bulk: bool = False
    weight: float = 0.0
    files: list = field(default_factory=list)
    dependencies_added: set = field(default_factory=set)

    @property
    def meaningful_lines(self) -> int:
        return self.meaningful_additions + self.meaningful_deletions

    @property
    def files_touched(self) -> int:
        return len(self.files)

    @property
    def categories(self) -> Counter:
        return Counter(f.category for f in self.files)

    @property
    def language_lines(self) -> Counter:
        """Own source/test lines per language."""
        out: Counter = Counter()
        for f in self.files:
            if f.language and f.category in {"source", "test"} and f.lines:
                out[f.language] += f.lines
        return out


def build_contribution(
    *,
    kind: str,
    repo: str,
    external: bool,
    url: str,
    message: str,
    date: Optional[str],
    files: list[dict],
) -> Optional[Contribution]:
    """Turn a commit or PR (with GitHub's `files[]` payload) into an evidence record. None = no evidence."""
    title = (message or "").strip().splitlines()[0][:200] if (message or "").strip() else "(no message)"
    c = Contribution(kind=kind, repo=repo, external=external, url=url, title=title, date=date)

    for f in files:
        info = classify_file(f.get("filename", ""))
        if info.category in IGNORED_CATEGORIES:
            continue
        additions, deletions = f.get("additions", 0), f.get("deletions", 0)
        patch = f.get("patch")

        imports = frozenset()
        if info.language and info.category in {"source", "test"}:
            imports = frozenset(extract_added_imports(info.language, patch))
        if info.category == "manifest":
            c.dependencies_added |= extract_added_dependencies(info.path, patch)

        if info.category in MEANINGFUL_CATEGORIES:
            c.meaningful_additions += additions
            c.meaningful_deletions += deletions
        else:
            c.other_lines += additions + deletions

        c.files.append(FileChange(info.path.lower(), info.category, info.language, additions + deletions, imports))

    if not c.files:
        return None

    c.type = classify_commit(message, list(c.categories), c.meaningful_additions, c.meaningful_deletions)
    c.bulk = is_bulk(c.files_touched, c.meaningful_lines)

    size = c.meaningful_additions + c.meaningful_deletions / 2 + c.other_lines / 4
    weight = math.log2(1 + size) * TYPE_MULTIPLIER.get(c.type, 0.5)
    if external and kind == "pr":
        weight *= EXTERNAL_PR_MULTIPLIER
    if c.bulk:
        weight *= BULK_MULTIPLIER
    c.weight = round(weight, 3)
    return c
