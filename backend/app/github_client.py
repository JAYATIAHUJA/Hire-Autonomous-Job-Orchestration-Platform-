import base64
from typing import Optional

import httpx

from .config import settings


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, rate_limited: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limited = rate_limited


class GitHubClient:
    def __init__(self, token: Optional[str] = None, transport: Optional[httpx.BaseTransport] = None):
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=settings.github_api_base,
            headers=headers,
            timeout=15.0,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _get(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        resp = self._client.get(url, params=params)
        if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubAPIError(
                "GitHub API rate limit exceeded. Add a personal access token to increase the limit.",
                status_code=resp.status_code,
                rate_limited=True,
            )
        if resp.status_code >= 400:
            raise GitHubAPIError(
                f"GitHub API error {resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            )
        return resp

    def _paginate(self, url: str, params: Optional[dict] = None, max_items: Optional[int] = None) -> list[dict]:
        items: list[dict] = []
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page = 1
        while True:
            params["page"] = page
            batch = self._get(url, params=params).json()
            if not isinstance(batch, list) or not batch:
                break
            items.extend(batch)
            if max_items and len(items) >= max_items:
                return items[:max_items]
            if len(batch) < params["per_page"]:
                break
            page += 1
        return items

    def get_authenticated_login(self) -> Optional[str]:
        try:
            return self._get("/user").json().get("login")
        except GitHubAPIError:
            return None

    def list_user_repos(self, username: str, authenticated: bool = False, max_items: int = 100) -> list[dict]:
        # /user/repos includes private repos but only works when the token belongs to `username`
        url = "/user/repos" if authenticated else f"/users/{username}/repos"
        params = {"sort": "pushed", "direction": "desc"}
        return self._paginate(url, params=params, max_items=max_items)

    def get_repo_languages(self, owner: str, repo: str) -> dict[str, int]:
        return self._get(f"/repos/{owner}/{repo}/languages").json()

    def list_user_commits(self, owner: str, repo: str, username: str, max_items: int = 300) -> list[dict]:
        try:
            return self._paginate(
                f"/repos/{owner}/{repo}/commits", params={"author": username}, max_items=max_items
            )
        except GitHubAPIError as e:
            # 409 = empty repository
            if e.status_code == 409:
                return []
            raise

    def get_commit(self, owner: str, repo: str, sha: str) -> dict:
        return self._get(f"/repos/{owner}/{repo}/commits/{sha}").json()

    def list_user_prs(self, username: str, owner: str, repo: str) -> list[dict]:
        query = f"author:{username} type:pr repo:{owner}/{repo}"
        return self._get("/search/issues", params={"q": query, "per_page": 100}).json().get("items", [])

    def get_file_text(self, owner: str, repo: str, path: str) -> Optional[str]:
        try:
            data = self._get(f"/repos/{owner}/{repo}/contents/{path}").json()
        except GitHubAPIError as e:
            if e.status_code == 404:
                return None
            raise
        if isinstance(data, dict) and data.get("encoding") == "base64" and "content" in data:
            return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
        return None
