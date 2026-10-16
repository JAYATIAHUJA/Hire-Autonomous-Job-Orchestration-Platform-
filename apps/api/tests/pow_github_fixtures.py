"""Serve the recorded GitHub responses in tests/fixtures/github/ through httpx.MockTransport.

File naming: the request path with "/" replaced by "__" (``/user/repos`` ->
``user__repos.json``). Commit details for a repo are bundled in
``repos__<owner>__<repo>__commit_details.json`` keyed by sha; GraphQL answers
come from ``graphql__<name>.json``. Every response carries a stable ETag and
honours ``If-None-Match`` with a 304, like GitHub does.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Optional

import httpx

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "github"
COMMIT_DETAIL = re.compile(r"^/repos/([^/]+)/([^/]+)/commits/([0-9a-f]{40})$")


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FixtureGitHub:
    def __init__(self, graphql: Optional[str] = "contributions"):
        self.graphql = graphql
        self.requests: list[httpx.Request] = []
        self.statuses: list[int] = []

    @property
    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self._respond(request)
        self.statuses.append(response.status_code)
        return response

    def _respond(self, request: httpx.Request) -> httpx.Response:
        body = self._body(request)
        if body is None:
            return httpx.Response(404, json={"message": "Not Found", "documentation_url": "https://docs.github.com/rest"})
        raw = json.dumps(body).encode()
        etag = '"' + hashlib.sha1(raw).hexdigest() + '"'
        if request.method == "GET" and request.headers.get("If-None-Match") == etag:
            return httpx.Response(304, headers={"ETag": etag})
        return httpx.Response(200, content=raw, headers={"ETag": etag, "Content-Type": "application/json"})

    def _body(self, request: httpx.Request):
        path = request.url.path
        if request.method == "POST" and path == "/graphql":
            return load(f"graphql__{self.graphql}.json") if self.graphql else None
        if m := COMMIT_DETAIL.match(path):
            bundle = FIXTURES / f"repos__{m[1]}__{m[2]}__commit_details.json"
            return json.loads(bundle.read_text(encoding="utf-8")).get(m[3]) if bundle.exists() else None
        name = path.strip("/").replace("/", "__") + ".json"
        if not (FIXTURES / name).exists():
            return None
        data = load(name)
        if isinstance(data, list):  # REST pagination: serve the requested page
            per_page = int(request.url.params.get("per_page", 30))
            page = int(request.url.params.get("page", 1))
            return data[(page - 1) * per_page: page * per_page]
        return data
