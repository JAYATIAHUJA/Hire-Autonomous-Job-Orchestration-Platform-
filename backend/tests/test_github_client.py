import httpx
import pytest

from app.github_client import GitHubAPIError, GitHubClient


def test_pagination_stops_on_short_page():
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages.append(page)
        if page == 1:
            return httpx.Response(200, json=[{"id": i} for i in range(100)])
        return httpx.Response(200, json=[{"id": 100}])

    client = GitHubClient(transport=httpx.MockTransport(handler))
    assert len(client._paginate("/users/octocat/repos")) == 101
    assert pages == [1, 2]


def test_pagination_respects_max_items():
    client = GitHubClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[{"id": i} for i in range(100)])))
    assert len(client._paginate("/x", max_items=150)) == 150


def test_rate_limit_is_flagged():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"X-RateLimit-Remaining": "0"}, json={"message": "rate limited"})

    client = GitHubClient(transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubAPIError) as exc:
        client.get_repo_languages("octocat", "hello")
    assert exc.value.rate_limited


def test_empty_repo_returns_no_commits():
    client = GitHubClient(transport=httpx.MockTransport(lambda r: httpx.Response(409, json={"message": "Git Repository is empty."})))
    assert client.list_user_commits("octocat", "empty", "octocat") == []


def test_missing_file_returns_none():
    client = GitHubClient(transport=httpx.MockTransport(lambda r: httpx.Response(404, json={})))
    assert client.get_file_text("octocat", "hello", "package.json") is None
