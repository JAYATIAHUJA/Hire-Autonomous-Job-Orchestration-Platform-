import asyncio
from datetime import datetime, timezone

from app.config import settings
from app.github_client import ETagCache, GitHubClient
from app.services.fetch_service import allocate_samples, fetch_contributions, repo_weight, spread_pick
from pow_github_fixtures import FixtureGitHub

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def fetch(gh: FixtureGitHub, token="user-token", **kwargs):
    client = GitHubClient(token=token, transport=gh.transport(), etag_cache=ETagCache(256))
    return asyncio.run(fetch_contributions("priyadev", token, client=client, **kwargs))


# --- allocation ----------------------------------------------------------------------

def test_heavier_repos_get_more_of_the_budget():
    alloc = allocate_samples({"big": 8.0, "mid": 4.0, "small": 1.0}, {"big": 100, "mid": 100, "small": 100}, budget=13)
    assert sum(alloc.values()) == 13
    assert alloc["big"] > alloc["mid"] > alloc["small"] >= 1


def test_unused_budget_flows_to_repos_that_can_use_it():
    alloc = allocate_samples({"big": 1.0, "tiny": 9.0}, {"big": 50, "tiny": 2}, budget=10)
    assert alloc == {"big": 8, "tiny": 2}


def test_every_repo_with_commits_gets_one_sample_when_budget_allows():
    alloc = allocate_samples({"a": 100.0, "b": 0.1, "c": 0.1}, {"a": 50, "b": 3, "c": 3}, budget=5)
    assert alloc["b"] == 1 and alloc["c"] == 1 and alloc["a"] == 3


def test_tight_budget_goes_to_the_heaviest_first():
    assert allocate_samples({"a": 1.0, "b": 5.0, "c": 3.0}, {"a": 9, "b": 9, "c": 9}, budget=2) == {"a": 0, "b": 1, "c": 1}


def test_empty_repos_get_nothing():
    assert allocate_samples({"a": 2.0, "empty": 0.0}, {"a": 4, "empty": 0}, budget=10) == {"a": 4, "empty": 0}


def test_spread_pick_covers_the_whole_history():
    items = list(range(10))
    assert spread_pick(items, 3) == [0, 4, 9]
    assert spread_pick(items, 1) == [0]
    assert spread_pick(items, 20) == items
    assert spread_pick([], 3) == []


def test_repo_weight_prefers_volume_stars_and_recency():
    fresh = {"pushed_at": "2026-09-20T00:00:00Z", "stargazers_count": 0}
    stale = {"pushed_at": "2023-09-20T00:00:00Z", "stargazers_count": 0}
    starred = {"pushed_at": "2026-09-20T00:00:00Z", "stargazers_count": 500}
    assert repo_weight(fresh, 100, NOW) > repo_weight(fresh, 10, NOW)
    assert repo_weight(fresh, 10, NOW) > repo_weight(stale, 10, NOW)
    assert repo_weight(starred, 10, NOW) > repo_weight(fresh, 10, NOW)
    assert repo_weight(fresh, 0, NOW) == 0.0


# --- fetch with fixtures ---------------------------------------------------------------

def test_full_run_records_sample_coverage_and_calendar():
    data = fetch(FixtureGitHub())
    cov = data["sample_coverage"]

    # 3 public non-fork repos; 10 + 3 + 6 commits listed, one of them a merge commit.
    assert cov["total_commits"] == 19
    assert cov["sampled_commits"] == 18
    assert cov["repos_total"] == 3 and cov["repos_sampled"] == 3
    assert cov["commits_last_year"] == 412
    assert cov["external_prs_sampled"] == 1
    assert data["calendar"][0] == {"date": "2026-09-20", "count": 3}
    assert data["private_repos"] == set()


def test_small_budget_is_spent_on_the_top_weighted_repos(monkeypatch):
    monkeypatch.setattr(settings, "full_commits_per_repo", 2)  # 3 repos -> 6 detail fetches
    gh = FixtureGitHub()
    data = fetch(gh)
    per_repo = {r["repo"]: r for r in data["sample_coverage"]["per_repo"]}

    assert data["sample_coverage"]["sampled_commits"] == 6
    assert per_repo["priyadev/shopfront"]["sampled"] >= per_repo["priyadev/ledger-api"]["sampled"]
    assert per_repo["priyadev/ledger-api"]["sampled"] >= per_repo["priyadev/fieldnotes-mobile"]["sampled"] >= 1
    detail_fetches = [p for p in gh.paths if p.count("/") == 5 and "/commits/" in p]
    assert len(detail_fetches) == 6


def test_graphql_per_repo_counts_pick_which_repos_are_analysed(monkeypatch):
    monkeypatch.setattr(settings, "full_max_repos", 1)
    data = fetch(FixtureGitHub())
    # shopfront has the most commits last year (180) even though salary-notes was pushed later.
    assert [p["full_name"] for p in data["projects"] if not p["is_external"]] == ["priyadev/shopfront"]


def test_private_repos_are_skipped_unless_opted_in():
    gh = FixtureGitHub()
    data = fetch(gh)
    assert not any("salary-notes" in p for p in gh.paths)
    assert all(not c.private for c in data["contributions"])


def test_opted_in_private_repo_is_analysed_but_flagged():
    data = fetch(FixtureGitHub(), include_private=True)
    private = [c for c in data["contributions"] if c.private]

    assert data["private_repos"] == {"priyadev/salary-notes"}
    assert private and {c.repo for c in private} == {"priyadev/salary-notes"}
    assert "2026-09-25T18:19:00Z" not in data["activity_dates"]  # private dates stay off the public timeline


def test_private_opt_in_needs_the_users_own_token():
    gh = FixtureGitHub()
    fetch(gh, token=None, include_private=True)
    assert "/users/priyadev/repos" in gh.paths and "/user/repos" not in gh.paths
    assert not any("salary-notes" in p for p in gh.paths)


def test_progress_only_moves_forward():
    seen: list[int] = []
    fetch(FixtureGitHub(), progress=seen.append)
    assert seen == sorted(seen) and seen[0] > 0 and seen[-1] < 100
