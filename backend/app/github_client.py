import asyncio
from typing import Optional

import httpx

from .config import settings


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, rate_limited: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limited = rate_limited


class GitHubClient:
    def __init__(self, token: Optional[str] = None, transport: Optional[httpx.AsyncBaseTransport] = None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=settings.github_api_base, headers=headers, timeout=30.0, transport=transport
        )
        self._semaphore = asyncio.Semaphore(settings.github_concurrency)

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def _get(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        async with self._semaphore:
            resp = await self._client.get(url, params=params)
        if resp.status_code in (403, 429) and (
            resp.headers.get("X-RateLimit-Remaining") == "0" or "rate limit" in resp.text.lower()
        ):
            raise GitHubAPIError(
                "GitHub API rate limit exceeded. Add a personal access token or try again later.",
                status_code=resp.status_code,
                rate_limited=True,
            )
        if resp.status_code >= 400:
            raise GitHubAPIError(f"GitHub API error {resp.status_code}: {resp.text[:200]}", status_code=resp.status_code)
        return resp

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
        query = f"author:{username} type:pr is:merged -user:{username}"
        resp = await self._get("/search/issues", params={"q": query, "sort": "created", "per_page": min(limit, 100)})
        return resp.json().get("items", [])[:limit]

    async def list_pr_files(self, owner: str, repo: str, number: int) -> list[dict]:
        return await self._paginate(f"/repos/{owner}/{repo}/pulls/{number}/files", max_items=300)
