"""Translate GitHub client failures into HTTP responses, so the router stays declarative."""

from fastapi import HTTPException

from ..github_client import GitHubAPIError


def http_error_for(error: GitHubAPIError, username: str) -> HTTPException:
    if error.rate_limited:
        return HTTPException(status_code=429, detail=str(error))
    if error.status_code == 404:
        return HTTPException(status_code=404, detail=f"GitHub user '{username}' not found.")
    if error.status_code == 401:
        return HTTPException(status_code=401, detail="Invalid GitHub token.")
    return HTTPException(status_code=502, detail=str(error))
