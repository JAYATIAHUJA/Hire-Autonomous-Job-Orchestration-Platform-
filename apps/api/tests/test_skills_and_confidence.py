from datetime import datetime, timedelta, timezone

from app.analysis.confidence import assess
from app.analysis.contribution import build_contribution
from app.analysis.highlights import top_contributions
from app.analysis.skills import infer_skills

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def file(name, adds=0, dels=0, patch=None):
    return {"filename": name, "additions": adds, "deletions": dels, "patch": patch}


def contribution(message, files, repo="ana/app", days_ago=10, kind="commit", external=False):
    return build_contribution(
        kind=kind, repo=repo, external=external, url=f"https://github.com/{repo}/x", message=message,
        date=iso(days_ago), files=files,
    )


def react_feature(repo="ana/app", days_ago=10, lines=300):
    body = "\n".join(["+import { useState } from 'react'"] + ["+  const x = 1"] * (lines - 1))
    return contribution("feat: build checkout form", [file("src/Checkout.tsx", lines, 0, body)], repo, days_ago)


def test_typo_in_react_repo_is_not_react_evidence():
    typo = contribution("fix typo", [file("src/App.tsx", 1, 1, "-const titel = 1\n+const title = 1")])
    skills = infer_skills([typo])

    assert "React" not in skills  # no React import added by this user
    tier, _ = assess(skills["TypeScript"], now=NOW)
    assert tier == "Limited"


def test_lockfiles_and_generated_files_are_ignored():
    assert contribution("update lock", [file("package-lock.json", 5000, 4000), file("dist/app.js", 900)]) is None


def test_imports_and_dependencies_drive_framework_detection():
    c = contribution(
        "Add API",
        [
            file("api/main.py", 80, 0, "+from fastapi import FastAPI\n+app = FastAPI()"),
            file("requirements.txt", 1, 0, "+fastapi>=0.111"),
            file("Dockerfile", 12, 0, "+FROM python:3.12"),
        ],
    )
    skills = infer_skills([c])

    assert {"Python", "FastAPI", "Docker"} <= skills.keys()
    assert "Imports fastapi in 1 changed file" in skills["FastAPI"].detected_via()
    assert "Added dependency fastapi" in skills["FastAPI"].detected_via()


def test_language_credit_is_proportional_within_a_commit():
    c = contribution(
        "Add dashboard",
        [file("web/Dashboard.tsx", 300, 0, "+x"), file("scripts/seed.py", 3, 0, "+x")],
    )
    skills = infer_skills([c])
    assert skills["TypeScript"].weight > 50 * skills["Python"].weight


def test_strong_tier_requires_substantial_code_plus_other_factors():
    contributions = [
        react_feature("ana/shop", days_ago=10),
        react_feature("ana/blog", days_ago=70),
        react_feature("ana/shop", days_ago=140),
    ]
    tier, factors = assess(infer_skills(contributions)["React"], now=NOW)

    met = {f["label"] for f in factors if f["met"]}
    assert met == {"Substantial own code", "Used across projects", "Sustained over time", "Recent", "Built features"}
    assert tier == "Strong"


def test_many_small_old_commits_without_substance_stay_moderate_at_most():
    contributions = [react_feature(f"ana/r{i}", days_ago=400 + 40 * i, lines=20) for i in range(5)]
    tier, factors = assess(infer_skills(contributions)["React"], now=NOW)
    assert not factors[0]["met"]
    assert tier == "Moderate"


def test_merged_external_pr_counts_as_acceptance_and_weighs_more():
    own = react_feature()
    pr = contribution(
        "Add keyboard navigation", [file("src/Menu.jsx", 300, 0, "+import React from 'react'")],
        repo="facebook/other", kind="pr", external=True,
    )
    skills = infer_skills([own, pr])
    _, factors = assess(skills["React"], now=NOW)

    assert next(f for f in factors if f["label"] == "Accepted by others")["met"]
    assert pr.weight > own.weight


def test_framework_and_testing_credit_only_counts_matching_files():
    c = contribution(
        "Add caching layer",
        [
            file("src/cache.ts", 400, 0, "+export const cache = new Map()"),
            file("src/cache.test.ts", 40, 0, "+import { describe } from 'vitest'"),
            file("src/Widget.tsx", 20, 0, "+import { memo } from 'react'"),
        ],
    )
    skills = infer_skills([c])

    assert skills["Automated Testing"].lines == 40
    assert skills["React"].lines == 20
    assert skills["TypeScript"].lines == 460


def test_dependency_without_code_is_weak_evidence():
    c = contribution("Add react", [file("package.json", 1, 0, '+    "react": "^18.3.1",'), file("src/a.ts", 200, 0)])
    skills = infer_skills([c])

    assert skills["React"].lines == 0
    assert skills["React"].feature_contributions == 0
    assert assess(skills["React"], now=NOW)[0] == "Limited"


def test_tiny_recent_feature_is_limited():
    c = contribution("Add footer", [file("site/index.html", 4, 0), file("app/main.py", 300, 0)])
    tier, factors = assess(infer_skills([c])["HTML/CSS"], now=NOW)
    assert sum(f["met"] for f in factors) == 2  # recent + built features
    assert tier == "Limited"


def test_bulk_imports_rank_below_real_work():
    bulk = contribution("Initial commit", [file(f"src/f{i}.py", 100) for i in range(120)])
    real = contribution("Add login flow", [file("src/login.py", 150, 10)])

    assert bulk.bulk and not real.bulk
    assert top_contributions([bulk, real], limit=1) == [real]
