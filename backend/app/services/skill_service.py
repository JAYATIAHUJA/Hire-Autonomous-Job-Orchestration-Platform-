import json
from functools import lru_cache
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parent.parent / "skill_rules.json"

# Linguist also reports these; they are rarely meaningful skill claims on their own.
IGNORED_LANGUAGES = {"Makefile", "Batchfile", "Procfile", "Dockerfile", "Shell", "PowerShell", "HTML", "CSS", "SCSS"}


@lru_cache
def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def match_skills(repo: dict, rules: dict) -> set[str]:
    repo_languages = set(repo["languages"])
    manifest = (repo.get("manifest_content") or "").lower()

    matched = {lang for lang in repo_languages if lang not in IGNORED_LANGUAGES}
    for skill, rule in rules.items():
        if repo_languages & set(rule.get("languages", [])):
            matched.add(skill)
        elif manifest and any(kw.lower() in manifest for kw in rule.get("keywords", [])):
            matched.add(skill)
    return matched


def infer_skills(repo_data: list[dict]) -> dict[str, dict]:
    rules = load_rules()
    skills: dict[str, dict] = {}

    for repo in repo_data:
        if repo["commit_count"] == 0:
            continue  # no authored commits = no evidence for this user
        sample = repo.get("sample_commit") or {}
        for skill in match_skills(repo, rules):
            entry = skills.setdefault(
                skill, {"repos": {}, "commit_count": 0, "pr_count": 0, "first_active": None, "last_active": None}
            )
            entry["commit_count"] += repo["commit_count"]
            entry["pr_count"] += repo["pr_count"]
            entry["repos"][repo["full_name"]] = {
                "repo_full_name": repo["full_name"],
                "repo_url": repo["url"],
                "commit_count": repo["commit_count"],
                "pr_count": repo["pr_count"],
                "sample_commit_url": sample.get("url"),
                "sample_commit_message": sample.get("message"),
            }
            first, last = repo["first_contribution"], repo["last_contribution"]
            if first and (entry["first_active"] is None or first < entry["first_active"]):
                entry["first_active"] = first
            if last and (entry["last_active"] is None or last > entry["last_active"]):
                entry["last_active"] = last

    return skills
