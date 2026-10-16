import asyncio
import math
from datetime import datetime, timezone
from typing import Callable, Optional

from ..analysis.contribution import Contribution, build_contribution
from ..analysis.roles import project_role
from ..config import AnalysisLimits, settings
from ..github_client import GitHubAPIError, GitHubClient

# progress(percent) — called as the run advances; percent only ever increases.
ProgressFn = Callable[[int], None]

# Progress milestones (percent) for a background run.
_P_REPOS, _P_TOTALS, _P_LISTED, _P_DETAILS, _P_EXTERNAL = 5, 15, 30, 85, 95


async def fetch_contributions(
    username: str,
    token: Optional[str],
    client: Optional[GitHubClient] = None,
    *,
    include_private: bool = False,
    progress: Optional[ProgressFn] = None,
) -> dict:
    """Pull the user's own commits and merged external PRs (with file diffs) and turn them into contributions.

    Commit detail fetches are the expensive part, so they are spent adaptively: the
    repos that carry most of the user's work get most of the budget (see
    ``allocate_samples``), and ``sample_coverage`` records how much was actually read.
    """
    report = progress or (lambda _p: None)
    limits = settings.limits(bool(token))
    client = client or GitHubClient(token=token)
    async with client:
        report(_P_REPOS)
        is_self = bool(token) and ((await client.get_authenticated_login()) or "").lower() == username.lower()
        repos = await client.list_user_repos(username, authenticated=is_self)
        # Private repos are dropped unless the user opted in: profiles are served publicly,
        # and their names and commit titles would leak. Opted-in private work feeds only
        # the owner's Evidence Index, flagged private (see pow_service).
        allow_private = include_private and is_self
        repos = [r for r in repos if not r.get("fork") and (allow_private or not r.get("private"))]

        totals = await _contribution_totals(client, username)
        report(_P_TOTALS)

        repo_commits = totals_by_repo(totals)
        repos = sorted(
            repos,
            key=lambda r: (repo_commits.get(r["full_name"].lower(), 0), r.get("pushed_at") or ""),
            reverse=True,
        )[: limits.max_repos]

        listings = await asyncio.gather(*(_list_repo(client, r, username) for r in repos))
        report(_P_LISTED)

        candidates = {r["full_name"]: [c for c in commits if len(c.get("parents", [])) <= 1]
                      for r, (commits, _) in zip(repos, listings)}
        weights = {r["full_name"]: repo_weight(r, len(commits)) for r, (commits, _) in zip(repos, listings)}
        budget = limits.commits_per_repo * len(repos)
        allocation = allocate_samples(weights, {k: len(v) for k, v in candidates.items()}, budget)

        to_fetch = sum(allocation.values()) or 1
        done = 0

        def detail_done() -> None:
            nonlocal done
            done += 1
            report(_P_LISTED + (_P_DETAILS - _P_LISTED) * done // to_fetch)

        repo_results = await asyncio.gather(*(
            _analyze_repo(client, r, username, commits, contributors,
                          spread_pick(candidates[r["full_name"]], allocation[r["full_name"]]), detail_done)
            for r, (commits, contributors) in zip(repos, listings)
        ))
        report(_P_DETAILS)

        analyzed = {r["full_name"].lower() for r in repos}
        external = await _analyze_external_prs(client, username, limits, skip_repos=analyzed)
        report(_P_EXTERNAL)

    projects = [r["project"] for r in repo_results] + external["projects"]
    contributions = [c for r in repo_results for c in r["contributions"]] + external["contributions"]
    activity_dates = [d for r in repo_results if not r["private"] for d in r["commit_dates"]]
    activity_dates += [c.date for c in external["contributions"] if c.date]
    return {
        "username": username,
        "analysis_mode": limits.mode,
        "projects": projects,
        "contributions": contributions,
        "activity_dates": activity_dates,
        "private_repos": {r["project"]["full_name"] for r in repo_results if r["private"]},
        "sample_coverage": {
            "sampled_commits": sum(r["sampled"] for r in repo_results),
            "total_commits": sum(r["listed"] for r in repo_results),
            "listing_capped": any(r["listed"] >= settings.max_commits_listed_per_repo for r in repo_results),
            "repos_sampled": sum(1 for r in repo_results if r["sampled"]),
            "repos_total": len(repos),
            "external_prs_sampled": len(external["contributions"]),
            "commits_last_year": (totals or {}).get("totalCommitContributions"),
            "per_repo": [
                {"repo": r["project"]["full_name"], "sampled": r["sampled"], "total": r["listed"]}
                for r in repo_results
            ],
        },
        "calendar": calendar_days(totals),
    }


async def _contribution_totals(client: GitHubClient, username: str) -> Optional[dict]:
    """GraphQL contributionsCollection, or None when it is unavailable (no token, API error)."""
    get_contributions = getattr(client, "get_contributions", None)  # minimal test doubles may lack it
    if get_contributions is None:
        return None
    try:
        return await get_contributions(username)
    except GitHubAPIError as e:
        if e.rate_limited or e.status_code == 404:
            raise
        return None  # totals are a nicety; REST sampling still works without them


def totals_by_repo(totals: Optional[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for entry in (totals or {}).get("commitContributionsByRepository") or []:
        name = ((entry.get("repository") or {}).get("nameWithOwner") or "").lower()
        if name:
            out[name] = (entry.get("contributions") or {}).get("totalCount", 0)
    return out


def calendar_days(totals: Optional[dict]) -> list[dict]:
    weeks = ((totals or {}).get("contributionCalendar") or {}).get("weeks") or []
    return [
        {"date": d["date"], "count": d["contributionCount"]}
        for w in weeks for d in w.get("contributionDays") or []
    ]


def repo_weight(repo: dict, user_commits: int, now: Optional[datetime] = None) -> float:
    """How much of the sampling budget a repo deserves: the user's own commit volume,
    nudged up by stars and down by staleness (half-life of one year)."""
    if user_commits <= 0:
        return 0.0
    now = now or datetime.now(timezone.utc)
    stars = repo.get("stargazers_count") or 0
    recency = 1.0
    if pushed := repo.get("pushed_at"):
        try:
            age_days = (now - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
            recency = 0.5 ** (max(age_days, 0) / 365)
        except ValueError:
            pass
    return math.log2(1 + user_commits) * (1 + math.log2(1 + stars) / 4) * (0.5 + 0.5 * recency)


def allocate_samples(weights: dict[str, float], available: dict[str, int], budget: int) -> dict[str, int]:
    """Split ``budget`` commit-detail fetches across repos in proportion to weight.

    Every repo with commits gets at least one sample (if the budget allows), no repo
    gets more than it has, and budget a small repo can't use flows to the heavier ones.
    Deterministic: ties break on repo name.
    """
    alloc = {k: 0 for k in weights}
    live = sorted((k for k in weights if available.get(k, 0) > 0 and weights[k] > 0),
                  key=lambda k: (-weights[k], k))
    remaining = budget
    for k in live:  # floor of one each, heaviest first
        if remaining <= 0:
            break
        alloc[k] = 1
        remaining -= 1
    while remaining > 0:
        open_repos = [k for k in live if alloc[k] < available[k]]
        if not open_repos:
            break
        total = sum(weights[k] for k in open_repos)
        shares = {k: remaining * weights[k] / total for k in open_repos}
        granted = 0
        for k in open_repos:
            extra = min(int(shares[k]), available[k] - alloc[k])
            alloc[k] += extra
            granted += extra
        if granted == 0:  # hand out the remainder one by one, largest fractional share first
            for k in sorted(open_repos, key=lambda k: (-(shares[k] - int(shares[k])), -weights[k], k)):
                if remaining - granted <= 0:
                    break
                if alloc[k] < available[k]:
                    alloc[k] += 1
                    granted += 1
        remaining -= granted
    return alloc


def spread_pick(items: list, k: int) -> list:
    """k items spread evenly across the list (newest first), so a sample covers the
    whole history rather than just last week's commits."""
    n = len(items)
    if k <= 0 or n == 0:
        return []
    if k >= n:
        return list(items)
    if k == 1:
        return [items[0]]
    return [items[round(i * (n - 1) / (k - 1))] for i in range(k)]


async def _list_repo(client: GitHubClient, repo: dict, username: str) -> tuple[list[dict], list[dict]]:
    owner, name = repo["owner"]["login"], repo["name"]
    commits, contributors = await asyncio.gather(
        client.list_user_commits(owner, name, username, max_items=settings.max_commits_listed_per_repo),
        client.list_contributors(owner, name),
    )
    return commits, contributors


async def _analyze_repo(
    client: GitHubClient,
    repo: dict,
    username: str,
    commits: list[dict],
    contributors: list[dict],
    sample: list[dict],
    on_detail: Callable[[], None],
) -> dict:
    owner, name, full_name = repo["owner"]["login"], repo["name"], repo["full_name"]
    private = bool(repo.get("private"))

    async def detail(sha: str) -> dict:
        d = await client.get_commit(owner, name, sha)
        on_detail()
        return d

    details = await asyncio.gather(*(detail(c["sha"]) for c in sample))

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
            c.private = private
            contributions.append(c)

    dates = [c["commit"]["author"]["date"] for c in commits if ((c.get("commit") or {}).get("author") or {}).get("date")]
    role, share = project_role(username, owner, len(commits), contributors)
    return {
        "project": _project(full_name, repo["html_url"], role, share, False, len(commits), contributions, dates),
        "contributions": contributions,
        "commit_dates": dates,
        "private": private,
        "sampled": len(sample),
        "listed": len(commits),
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
