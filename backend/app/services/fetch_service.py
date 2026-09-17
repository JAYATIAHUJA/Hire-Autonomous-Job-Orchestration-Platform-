import asyncio
from typing import Optional

from ..analysis.contribution import Contribution, build_contribution
from ..analysis.roles import project_role
from ..config import AnalysisLimits, settings
from ..github_client import GitHubAPIError, GitHubClient


async def fetch_contributions(username: str, token: Optional[str], client: Optional[GitHubClient] = None) -> dict:
    """Pull the user's own commits and merged external PRs (with file diffs) and turn them into contributions."""
    limits = settings.limits(bool(token))
    client = client or GitHubClient(token=token)
    async with client:
        is_self = bool(token) and ((await client.get_authenticated_login()) or "").lower() == username.lower()
        repos = await client.list_user_repos(username, authenticated=is_self)
        repos = sorted((r for r in repos if not r.get("fork")), key=lambda r: r.get("pushed_at") or "", reverse=True)
        repos = repos[: limits.max_repos]

        repo_results = await asyncio.gather(*(_analyze_repo(client, r, username, limits) for r in repos))
        analyzed = {r["full_name"].lower() for r in repos}
        external = await _analyze_external_prs(client, username, limits, skip_repos=analyzed)

    projects = [r["project"] for r in repo_results] + external["projects"]
    contributions = [c for r in repo_results for c in r["contributions"]] + external["contributions"]
    activity_dates = [d for r in repo_results for d in r["commit_dates"]] + [c.date for c in external["contributions"] if c.date]
    return {
        "username": username,
        "analysis_mode": limits.mode,
        "projects": projects,
        "contributions": contributions,
        "activity_dates": activity_dates,
    }


async def _analyze_repo(client: GitHubClient, repo: dict, username: str, limits: AnalysisLimits) -> dict:
    owner, name, full_name = repo["owner"]["login"], repo["name"], repo["full_name"]

    commits, contributors = await asyncio.gather(
        client.list_user_commits(owner, name, username, max_items=settings.max_commits_listed_per_repo),
        client.list_contributors(owner, name),
    )
    candidates = [c for c in commits if len(c.get("parents", [])) <= 1][: limits.commits_per_repo]
    details = await asyncio.gather(*(client.get_commit(owner, name, c["sha"]) for c in candidates))

    contributions: list[Contribution] = []
    for d in details:
        commit = d.get("commit") or {}
        c = build_contribution(
            kind="commit",
            repo=full_name,
            external=False,
            url=d.get("html_url", ""),
            message=commit.get("message", ""),
            date=(commit.get("author") or {}).get("date"),
            files=d.get("files") or [],
        )
        if c:
            contributions.append(c)

    dates = [c["commit"]["author"]["date"] for c in commits if ((c.get("commit") or {}).get("author") or {}).get("date")]
    role, share = project_role(username, owner, len(commits), contributors)
    return {
        "project": _project(full_name, repo["html_url"], role, share, False, len(commits), contributions, dates),
        "contributions": contributions,
        "commit_dates": dates,
    }


async def _analyze_external_prs(client: GitHubClient, username: str, limits: AnalysisLimits, skip_repos: set) -> dict:
    items = await client.search_external_merged_prs(username, limits.external_prs)
    items = [i for i in items if _repo_from_api_url(i["repository_url"]).lower() not in skip_repos]

    async def one(item: dict) -> Optional[Contribution]:
        full_name = _repo_from_api_url(item["repository_url"])
        owner, name = full_name.split("/", 1)
        try:
            files = await client.list_pr_files(owner, name, item["number"])
        except GitHubAPIError as e:
            if e.rate_limited:
                raise
            return None
        return build_contribution(
            kind="pr",
            repo=full_name,
            external=True,
            url=item["html_url"],
            message=item.get("title", ""),
            date=(item.get("pull_request") or {}).get("merged_at") or item.get("closed_at"),
            files=files,
        )

    contributions = [c for c in await asyncio.gather(*(one(i) for i in items)) if c]
    by_repo: dict[str, list[Contribution]] = {}
    for c in contributions:
        by_repo.setdefault(c.repo, []).append(c)
    projects = [
        _project(repo, f"https://github.com/{repo}", "External contributor", None, True, len(cs), cs,
                 [c.date for c in cs if c.date])
        for repo, cs in by_repo.items()
    ]
    return {"projects": projects, "contributions": contributions}


def _project(full_name, url, role, share, external, count, contributions, dates) -> dict:
    languages: dict[str, int] = {}
    for c in contributions:
        for lang, lines in c.language_lines.items():
            languages[lang] = languages.get(lang, 0) + lines
    return {
        "full_name": full_name,
        "url": url,
        "role": role,
        "ownership_share": share,
        "is_external": external,
        "contribution_count": count,
        "meaningful_lines": sum(c.meaningful_lines for c in contributions),
        "primary_language": max(languages, key=languages.get) if languages else None,
        "first_contribution": min(dates) if dates else None,
        "last_contribution": max(dates) if dates else None,
    }


def _repo_from_api_url(url: str) -> str:
    return url.split("/repos/", 1)[1]
