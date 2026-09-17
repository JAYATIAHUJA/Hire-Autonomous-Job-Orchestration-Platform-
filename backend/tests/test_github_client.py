import asyncio

import httpx
import pytest

from app.github_client import GitHubAPIError, GitHubClient


def run(coro):
    return asyncio.run(coro)


def client_for(handler) -> GitHubClient:
    return GitHubClient(transport=httpx.MockTransport(handler))


def test_pagination_stops_on_short_page():
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages.append(page)
        return httpx.Response(200, json=[{"id": i} for i in range(100 if page == 1 else 1)])

    assert len(run(client_for(handler)._paginate("/users/octocat/repos"))) == 101
    assert pages == [1, 2]


def test_pagination_respects_max_items():
    client = client_for(lambda r: httpx.Response(200, json=[{"id": i} for i in range(100)]))
    assert len(run(client._paginate("/x", max_items=150))) == 150


def test_rate_limit_is_flagged():
    client = client_for(lambda r: httpx.Response(403, headers={"X-RateLimit-Remaining": "0"}, json={}))
    with pytest.raises(GitHubAPIError) as exc:
        run(client.get_commit("octocat", "hello", "abc"))
    assert exc.value.rate_limited


def test_empty_repo_returns_no_commits():
    client = client_for(lambda r: httpx.Response(409, json={"message": "Git Repository is empty."}))
    assert run(client.list_user_commits("octocat", "empty", "octocat", max_items=10)) == []


def test_contributors_tolerate_errors_and_no_content():
    assert run(client_for(lambda r: httpx.Response(204)).list_contributors("o", "r")) == []
    assert run(client_for(lambda r: httpx.Response(403, json={"message": "too large"})).list_contributors("o", "r")) == []


def test_external_pr_search_query():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["q"] = request.url.params["q"]
        return httpx.Response(200, json={"items": [{"number": 1}, {"number": 2}]})

    assert len(run(client_for(handler).search_external_merged_prs("ana", limit=1))) == 1
    assert seen["q"] == "author:ana type:pr is:merged -user:ana"
