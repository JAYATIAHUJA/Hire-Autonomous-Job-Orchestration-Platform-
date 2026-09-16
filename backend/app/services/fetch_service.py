from typing import Optional

from ..config import settings
from ..github_client import GitHubAPIError, GitHubClient

LANGUAGE_MANIFESTS = {
    "JavaScript": "package.json",
    "TypeScript": "package.json",
    "Vue": "package.json",
    "Python": "requirements.txt",
    "Jupyter Notebook": "requirements.txt",
    "Java": "pom.xml",
    "Kotlin": "build.gradle",
    "Go": "go.mod",
    "Ruby": "Gemfile",
    "Rust": "Cargo.toml",
}


def fetch_user_data(username: str, token: Optional[str], client: Optional[GitHubClient] = None) -> dict:
    owns_client = client is None
    client = client or GitHubClient(token=token)
    try:
        is_self = bool(token) and (client.get_authenticated_login() or "").lower() == username.lower()
        repos = client.list_user_repos(username, authenticated=is_self)
        repos = [r for r in repos if not r.get("fork")]
        repos.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
        repos = repos[: settings.max_repos_per_user]

        return {"username": username, "repos": [_fetch_repo(client, r, username) for r in repos]}
    finally:
        if owns_client:
            client.close()


def _fetch_repo(client: GitHubClient, repo: dict, username: str) -> dict:
    owner, name = repo["owner"]["login"], repo["name"]

    languages = client.get_repo_languages(owner, name)
    commits = client.list_user_commits(owner, name, username, max_items=settings.max_commits_per_repo)

    # Per-commit stats cost one request each, so sample and extrapolate.
    sample = commits[: settings.commit_stats_sample_size]
    additions = deletions = 0
    sample_commit = None
    for c in sample:
        detail = client.get_commit(owner, name, c["sha"])
        stats = detail.get("stats", {})
        additions += stats.get("additions", 0)
        deletions += stats.get("deletions", 0)
        message = detail.get("commit", {}).get("message") or ""
        if sample_commit is None and message:
            sample_commit = {"url": detail.get("html_url"), "message": message.splitlines()[0][:120]}
    if sample:
        scale = len(commits) / len(sample)
        additions, deletions = int(additions * scale), int(deletions * scale)

    try:
        pr_count = len(client.list_user_prs(username, owner, name))
    except GitHubAPIError as e:
        if e.rate_limited:
            raise
        pr_count = 0

    primary_language = max(languages, key=languages.get) if languages else None
    manifest_path = LANGUAGE_MANIFESTS.get(primary_language)
    manifest_content = client.get_file_text(owner, name, manifest_path) if manifest_path else None

    dates = [c["commit"]["author"]["date"] for c in commits if (c.get("commit") or {}).get("author")]

    return {
        "full_name": repo["full_name"],
        "url": repo["html_url"],
        "languages": languages,
        "primary_language": primary_language,
        "commit_count": len(commits),
        "additions": additions,
        "deletions": deletions,
        "pr_count": pr_count,
        "first_contribution": min(dates) if dates else None,
        "last_contribution": max(dates) if dates else None,
        "commit_dates": dates,
        "sample_commit": sample_commit,
        "manifest_content": manifest_content,
    }
