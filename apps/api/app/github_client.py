import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import Awaitable, Callable, Optional

import httpx

from .config import settings

CONTRIBUTIONS_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
      commitContributionsByRepository(maxRepositories: 100) {
        repository { nameWithOwner isPrivate isFork }
        contributions { totalCount }
      }
    }
  }
}
"""


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, rate_limited: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limited = rate_limited


class ETagCache:
    """Remembers (ETag, body) per request so a repeat GET can be conditional.

    GitHub answers ``If-None-Match`` with 304, which does not count against the
    rate limit. Entries are keyed by a hash of the credential as well as the URL,
    so one user's private responses are never served to another.
    """

    def __init__(self, max_entries: int):
        self.max_entries = max_entries
        self._entries: OrderedDict[str, tuple[str, bytes, dict]] = OrderedDict()

    def get(self, key: str) -> Optional[tuple[str, bytes, dict]]:
        entry = self._entries.get(key)
        if entry:
            self._entries.move_to_end(key)
        return entry

    def put(self, key: str, etag: str, body: bytes, headers: dict) -> None:
        self._entries[key] = (etag, body, headers)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)


# Shared by every client in the process (the worker analyses many users in turn).
default_etag_cache = ETagCache(settings.github_etag_cache_size)


class GitHubClient:
    def __init__(
        self,
        token: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        etag_cache: Optional[ETagCache] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.has_token = bool(token)
        self._credential = hashlib.sha256((token or "").encode()).hexdigest()[:16]
        self._client = httpx.AsyncClient(
            base_url=settings.github_api_base, headers=headers, timeout=30.0, transport=transport
        )
        self._semaphore = asyncio.Semaphore(settings.github_concurrency)
        self._etags = etag_cache if etag_cache is not None else default_etag_cache
        self._sleep = sleep

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Send one request, waiting out GitHub's back-off signals a bounded number of times.

        403/429 with ``Retry-After`` (secondary limits) or an exhausted primary limit
        with ``X-RateLimit-Reset`` are retried after the advertised wait, as long as
        that wait is under ``github_max_backoff_seconds``. Anything longer fails fast
        as rate-limited, so a background run reports it instead of hanging for an hour.
        """
        for attempt in range(settings.github_max_retries + 1):
            async with self._semaphore:
                resp = await self._client.request(method, url, **kwargs)
            if resp.status_code not in (403, 429):
                return resp
            wait = _backoff_seconds(resp)
            limited = wait is not None or resp.headers.get("X-RateLimit-Remaining") == "0" or "rate limit" in resp.text.lower()
            if not limited:
                return resp  # a plain 403 (forbidden), not a rate limit
            if wait is None or wait > settings.github_max_backoff_seconds or attempt == settings.github_max_retries:
                raise GitHubAPIError(
                    "GitHub API rate limit exceeded. Add a personal access token or try again later.",
                    status_code=resp.status_code,
                    rate_limited=True,
                )
            await self._sleep(wait)
        raise AssertionError("unreachable")

    async def _get(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        key = f"{self._credential} {url} {sorted((params or {}).items())}"
        cached = self._etags.get(key)
        headers = {"If-None-Match": cached[0]} if cached else {}
        resp = await self._send("GET", url, params=params, headers=headers)
        if resp.status_code == 304 and cached:
            return httpx.Response(200, content=cached[1], headers=cached[2], request=resp.request)
        if resp.status_code >= 400:
            raise GitHubAPIError(f"GitHub API error {resp.status_code}: {resp.text[:200]}", status_code=resp.status_code)
        if etag := resp.headers.get("ETag"):
            self._etags.put(key, etag, resp.content, {"Content-Type": resp.headers.get("Content-Type", "application/json")})
        return resp

    async def graphql(self, query: str, variables: dict) -> dict:
        if not self.has_token:
            raise GitHubAPIError("GitHub GraphQL needs a token.", status_code=401)
        resp = await self._send("POST", "/graphql", json={"query": query, "variables": variables})
        if resp.status_code >= 400:
            raise GitHubAPIError(f"GitHub GraphQL error {resp.status_code}: {resp.text[:200]}", status_code=resp.status_code)
        body = resp.json()
        if body.get("errors"):
            messages = "; ".join(e.get("message", "") for e in body["errors"])
            not_found = any(e.get("type") == "NOT_FOUND" for e in body["errors"])
            raise GitHubAPIError(f"GitHub GraphQL error: {messages[:200]}", status_code=404 if not_found else 502)
        return body.get("data") or {}

    async def get_contributions(self, username: str) -> Optional[dict]:
        """Last-year totals, calendar and per-repo commit counts. None without a token (GraphQL needs one)."""
        if not self.has_token:
            return None
        data = await self.graphql(CONTRIBUTIONS_QUERY, {"login": username})
        user = data.get("user")
        if not user:
            raise GitHubAPIError(f"GitHub user '{username}' not found.", status_code=404)
        return user["contributionsCollection"]

    async def _paginate(self, url: str, params: Optional[dict] = None, max_items: Optional[int] = None) -> list[dict]:
        items: list[dict] = []
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page = 1
        while True:
            params["page"] = page
            resp = await self._get(url, params=params)
            batch = resp.json() if resp.status_code != 204 else []
            if not isinstance(batch, list) or not batch:
                break
            items.extend(batch)
            if max_items and len(items) >= max_items:
                return items[:max_items]
            if len(batch) < params["per_page"]:
                break
            page += 1
        return items

    async def get_authenticated_login(self) -> Optional[str]:
        try:
            return (await self._get("/user")).json().get("login")
        except GitHubAPIError as e:
            if e.rate_limited:
                raise
            return None

    async def list_user_repos(self, username: str, authenticated: bool = False, max_items: int = 100) -> list[dict]:
        # /user/repos includes private repos but only when the token belongs to `username`
        url = "/user/repos" if authenticated else f"/users/{username}/repos"
        return await self._paginate(url, params={"sort": "pushed", "direction": "desc"}, max_items=max_items)

    async def list_user_commits(self, owner: str, repo: str, username: str, max_items: int) -> list[dict]:
        try:
            return await self._paginate(
                f"/repos/{owner}/{repo}/commits", params={"author": username}, max_items=max_items
            )
        except GitHubAPIError as e:
            if e.status_code == 409:  # empty repository
                return []
            raise

    async def get_commit(self, owner: str, repo: str, sha: str) -> dict:
        return (await self._get(f"/repos/{owner}/{repo}/commits/{sha}")).json()

    async def list_contributors(self, owner: str, repo: str) -> list[dict]:
        try:
            return await self._paginate(f"/repos/{owner}/{repo}/contributors", max_items=100)
        except GitHubAPIError as e:
            if e.rate_limited:
                raise
            return []  # very large repos can refuse contributor stats

    async def search_external_merged_prs(self, username: str, limit: int) -> list[dict]:
        if limit <= 0:
            return []
        # is:public: with a token, search also returns PRs in private repos the token can see.
        query = f"author:{username} type:pr is:merged is:public -user:{username}"
        resp = await self._get("/search/issues", params={"q": query, "sort": "created", "per_page": min(limit, 100)})
        return resp.json().get("items", [])[:limit]

    async def list_pr_files(self, owner: str, repo: str, number: int) -> list[dict]:
        return await self._paginate(f"/repos/{owner}/{repo}/pulls/{number}/files", max_items=300)


def _backoff_seconds(resp: httpx.Response) -> Optional[float]:
    """Seconds GitHub asked us to wait, or None when it gave no usable hint."""
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            return None
    if resp.headers.get("X-RateLimit-Remaining") == "0" and (reset := resp.headers.get("X-RateLimit-Reset")):
        try:
            return max(float(reset) - time.time(), 0.0) + 1.0
        except ValueError:
            return None
    return None
