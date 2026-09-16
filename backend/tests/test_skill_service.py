from app.services.skill_service import infer_skills


def make_repo(**overrides):
    repo = {
        "full_name": "user/api",
        "url": "https://github.com/user/api",
        "languages": {"Python": 1000, "Dockerfile": 50},
        "commit_count": 15,
        "pr_count": 2,
        "first_contribution": "2024-01-01T00:00:00Z",
        "last_contribution": "2024-06-01T00:00:00Z",
        "manifest_content": "fastapi>=0.1\nuvicorn",
        "sample_commit": {"url": "https://github.com/user/api/commit/abc", "message": "Add endpoint"},
    }
    repo.update(overrides)
    return repo


def test_languages_and_manifest_keywords_become_skills():
    skills = infer_skills([make_repo()])

    assert {"Python", "FastAPI", "Docker"} <= skills.keys()
    assert "Dockerfile" not in skills
    assert "Django" not in skills
    evidence = skills["FastAPI"]["repos"]["user/api"]
    assert evidence["sample_commit_url"] == "https://github.com/user/api/commit/abc"


def test_evidence_aggregates_across_repos():
    skills = infer_skills(
        [
            make_repo(),
            make_repo(
                full_name="user/ml",
                url="https://github.com/user/ml",
                commit_count=5,
                pr_count=1,
                first_contribution="2023-03-01T00:00:00Z",
                last_contribution="2025-02-01T00:00:00Z",
                manifest_content="numpy\npandas",
            ),
        ]
    )

    python = skills["Python"]
    assert python["commit_count"] == 20
    assert python["pr_count"] == 3
    assert len(python["repos"]) == 2
    assert python["first_active"] == "2023-03-01T00:00:00Z"
    assert python["last_active"] == "2025-02-01T00:00:00Z"
    assert "Pandas" in skills and "FastAPI" in skills


def test_repos_without_authored_commits_give_no_evidence():
    assert infer_skills([make_repo(commit_count=0)]) == {}
