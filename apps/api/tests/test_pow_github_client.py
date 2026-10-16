import asyncio
import json
import time

import httpx
import pytest

from app.config import settings
from app.github_client import ETagCache, GitHubAPIError, GitHubClient
from app.services import github_tokens
from pow_github_fixtures import FixtureGitHub, load


def run(coro):
    return asyncio.run(coro)


class Sleeps:
    def __init__(self):
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def client(handler, token=None, cache=None, sleep=None) -> GitHubClient:
    return GitHubClient(token=token, transport=httpx.MockTransport(handler), etag_cache=cache or ETagCache(64),
                        sleep=sleep or Sleeps())


# --- ETag caching ----------------------------------------------------------------

def test_repeat_get_is_conditional_and_served_from_cache():
    gh, cache = FixtureGitHub(), ETagCache(64)

    async def twice():
        async with client(gh.handle, cache=cache) as c1:
            first = await c1.get_commit("priyadev", "shopfront", load("repos__priyadev__shopfront__commits.json")[0]["sha"])
        async with client(gh.handle, cache=cache) as c2:
            second = await c2.get_commit("priyadev", "shopfront", first["sha"])
        return first, second

    first, second = run(twice())
    assert first == second
    assert "If-None-Match" not in gh.requests[0].headers
    assert gh.statuses == [200, 304]  # the repeat was conditional: a 304 costs no rate limit


def test_etag_cache_is_partitioned_by_credential():
    gh, cache = FixtureGitHub(), ETagCache(64)

    async def go():
        async with client(gh.handle, token="user-a", cache=cache) as a:
            await a.list_user_repos("priyadev", authenticated=True)
        async with client(gh.handle, token="user-b", cache=cache) as b:
            await b.list_user_repos("priyadev", authenticated=True)

    run(go())
    assert all("If-None-Match" not in r.headers for r in gh.requests)


def test_etag_cache_evicts_oldest():
    cache = ETagCache(2)
    for k in "abc":
        cache.put(k, '"e"', b"{}", {})
    assert cache.get("a") is None and cache.get("c") is not None


# --- back-off ----------------------------------------------------------------------

def test_secondary_rate_limit_waits_for_retry_after_then_succeeds():
    responses = iter([
        httpx.Response(403, headers={"Retry-After": "7"}, json=load("rate_limited_secondary.json")),
        httpx.Response(200, json={"login": "priyadev"}),
    ])
    sleeps = Sleeps()
    assert run(client(lambda r: next(responses), sleep=sleeps).get_authenticated_login()) == "priyadev"
    assert sleeps.calls == [7.0]


def test_429_with_retry_after_is_retried():
    responses = iter([httpx.Response(429, headers={"Retry-After": "2"}, json={}), httpx.Response(200, json={"sha": "x"})])
    sleeps = Sleeps()
    assert run(client(lambda r: next(responses), sleep=sleeps).get_commit("o", "r", "x")) == {"sha": "x"}
    assert sleeps.calls == [2.0]


def test_primary_limit_waits_until_reset_when_close():
    reset = str(int(time.time()) + 5)
    responses = iter([
        httpx.Response(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset}, json={"message": "API rate limit exceeded"}),
        httpx.Response(200, json={"sha": "x"}),
    ])
    sleeps = Sleeps()
    run(client(lambda r: next(responses), sleep=sleeps).get_commit("o", "r", "x"))
    assert len(sleeps.calls) == 1 and 0 < sleeps.calls[0] <= 7


def test_long_waits_fail_fast_as_rate_limited():
    reset = str(int(time.time()) + 3600)
    handler = lambda r: httpx.Response(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset}, json={})
    sleeps = Sleeps()
    with pytest.raises(GitHubAPIError) as exc:
        run(client(handler, sleep=sleeps).get_commit("o", "r", "x"))
    assert exc.value.rate_limited and sleeps.calls == []


def test_retries_are_bounded(monkeypatch):
    monkeypatch.setattr(settings, "github_max_retries", 2)
    sleeps = Sleeps()
    handler = lambda r: httpx.Response(429, headers={"Retry-After": "1"}, json={})
    with pytest.raises(GitHubAPIError) as exc:
        run(client(handler, sleep=sleeps).get_commit("o", "r", "x"))
    assert exc.value.rate_limited and sleeps.calls == [1.0, 1.0]


def test_plain_forbidden_is_not_retried():
    sleeps = Sleeps()
    handler = lambda r: httpx.Response(403, json={"message": "Resource not accessible by integration"})
    with pytest.raises(GitHubAPIError) as exc:
        run(client(handler, sleep=sleeps).get_commit("o", "r", "x"))
    assert exc.value.status_code == 403 and not exc.value.rate_limited and sleeps.calls == []


# --- GraphQL -------------------------------------------------------------------------

def test_contributions_collection_via_graphql():
    gh = FixtureGitHub()
    totals = run(client(gh.handle, token="user-token").get_contributions("priyadev"))

    assert totals["totalCommitContributions"] == 412
    assert totals["contributionCalendar"]["weeks"][0]["contributionDays"][0] == {"date": "2026-09-20", "contributionCount": 3}
    request = gh.requests[0]
    assert (request.method, request.url.path) == ("POST", "/graphql")
    assert request.headers["Authorization"] == "Bearer user-token"
    assert b"contributionsCollection" in request.content and json.loads(request.content)["variables"] == {"login": "priyadev"}


def test_graphql_is_skipped_without_a_token():
    gh = FixtureGitHub()
    assert run(client(gh.handle).get_contributions("priyadev")) is None
    assert gh.requests == []


def test_graphql_unknown_user_is_404():
    gh = FixtureGitHub(graphql="user_not_found")
    with pytest.raises(GitHubAPIError) as exc:
        run(client(gh.handle, token="t").get_contributions("no-such-user-xyz"))
    assert exc.value.status_code == 404


# --- token seam ------------------------------------------------------------------------

def test_user_token_wins_over_app_token(monkeypatch):
    monkeypatch.setattr(settings, "github_app_token", "app-token")
    github_tokens.set_user_token_provider(lambda db, account_id: "user-token" if account_id == 7 else None)
    try:
        assert github_tokens.resolve_token(None, 7) == ("user-token", "user")
        assert github_tokens.resolve_token(None, 8) == ("app-token", "app")
    finally:
        github_tokens.set_user_token_provider(None)


def test_no_tokens_means_unauthenticated(monkeypatch):
    monkeypatch.setattr(settings, "github_app_token", "")
    assert github_tokens.resolve_token(None, 1) == (None, "none")
