"""Online presence: GitHub username + personal access token, LinkedIn, website, portfolio and
other links, given directly instead of through OAuth."""

import hashlib

import pytest
from cryptography.fernet import Fernet

from app.auth import presence
from app.config import settings
from app.services import github_tokens
from auth_helpers import app_db, create_account, login_as, memory_client

pytestmark = pytest.mark.enforce_consent

NOTICE_HASH = hashlib.sha256(b"notice").hexdigest()
GITHUB_IDS = {"tok_priya": ("priyadev", 101), "tok_bob": ("bobdev", 202)}


def consent(**purposes):
    return {"notice_version": "v1", "notice_hash": NOTICE_HASH,
            "purposes": {"github": False, "resume": False, "email": False, **purposes}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())

    async def account_for_token(token):
        if token not in GITHUB_IDS:
            raise ValueError("GitHub rejected this token.")
        return GITHUB_IDS[token]

    async def user_exists(username):
        return username.lower() in {"priyadev", "bobdev", "octocat"}

    monkeypatch.setattr(presence, "github_account_for_token", account_for_token)
    monkeypatch.setattr(presence, "github_user_exists", user_exists)
    with memory_client() as c:
        c.alice = create_account(c, "alice@example.com")
        c.bob = create_account(c, "bob@example.com")
        login_as(c, c.alice)
        yield c
    from app.auth.tokens import register_github_providers

    register_github_providers()


def put(client, **body):
    return client.put("/v1/me/online-presence", json=body)


def test_links_are_cleaned_saved_and_land_in_the_profile(client):
    resp = put(client, github_username="octocat", linkedin="priya-sharma", website="priya.dev",
               portfolio="https://dribbble.com/priya", others=[{"label": "LeetCode", "url": "leetcode.com/u/priya"}])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {
        "github_username": "octocat",
        "github_token_saved": False,
        "linkedin": "https://www.linkedin.com/in/priya-sharma",
        "website": "https://priya.dev",
        "portfolio": "https://dribbble.com/priya",
        "others": [{"label": "LeetCode", "url": "https://leetcode.com/u/priya"}],
        "from_resume": False,
    }
    assert client.get("/v1/me/online-presence").json() == body

    links = client.get("/v1/profile").json()["profile"]["identity"]["links"]
    assert {(l["network"], l["url"]) for l in links} == {
        ("github", "https://github.com/octocat"),
        ("linkedin", "https://www.linkedin.com/in/priya-sharma"),
        ("website", "https://priya.dev"),
        ("portfolio", "https://dribbble.com/priya"),
        ("other", "https://leetcode.com/u/priya"),
    }


def test_saving_again_replaces_the_previous_links(client):
    put(client, website="old.dev", others=[{"label": "X", "url": "x.com/priya"}])
    put(client, website="new.dev")
    body = client.get("/v1/me/online-presence").json()
    assert body["website"] == "https://new.dev" and body["others"] == []
    assert len(client.get("/v1/profile").json()["profile"]["identity"]["links"]) == 1


@pytest.mark.parametrize("field,value,message", [
    ("linkedin", "https://twitter.com/priya", "linkedin.com"),
    ("website", "not a url", "web address"),
    ("github_username", "bad name!", "valid GitHub username"),
    ("github_username", "nobody-here", "no GitHub account called @nobody-here"),
])
def test_bad_input_is_a_clear_422(client, field, value, message):
    resp = put(client, **{field: value})
    assert resp.status_code == 422
    assert message in resp.json()["detail"]


def test_a_token_needs_github_consent(client):
    resp = put(client, github_username="priyadev", github_token="tok_priya")
    assert resp.status_code == 403
    assert "Analyse my GitHub" in resp.json()["detail"]


def test_a_verified_token_is_stored_encrypted_and_never_returned(client):
    client.post("/v1/me/consents", json=consent(github=True))
    resp = put(client, github_username="PriyaDev", github_token="tok_priya")
    assert resp.status_code == 200, resp.text
    assert resp.json()["github_token_saved"] is True
    assert resp.json()["github_username"] == "priyadev"  # GitHub's spelling wins
    assert "tok_priya" not in resp.text
    assert "github" in client.get("/v1/me").json()["identities"]

    with app_db(client) as db:
        assert github_tokens.resolve_token(db, client.alice.id) == ("tok_priya", "user")
        assert github_tokens.linked_login(db, client.alice.id) == "priyadev"

    # Saving links later without re-entering the token keeps it.
    assert put(client, github_username="priyadev", website="priya.dev").json()["github_token_saved"] is True


def test_a_token_for_someone_else_is_refused(client):
    client.post("/v1/me/consents", json=consent(github=True))
    resp = put(client, github_username="priyadev", github_token="tok_bob")
    assert resp.status_code == 422
    assert "belongs to @bobdev" in resp.json()["detail"]
    assert put(client, github_token="bad-token").status_code == 422


def test_one_github_account_cannot_back_two_hire_accounts(client):
    client.post("/v1/me/consents", json=consent(github=True))
    assert put(client, github_token="tok_priya").status_code == 200
    login_as(client, client.bob)
    client.post("/v1/me/consents", json=consent(github=True))
    resp = put(client, github_token="tok_priya")
    assert resp.status_code == 409


def test_removing_or_changing_the_username_drops_the_token(client):
    client.post("/v1/me/consents", json=consent(github=True))
    put(client, github_token="tok_priya")
    assert put(client, github_username="priyadev", clear_github_token=True).json()["github_token_saved"] is False
    with app_db(client) as db:
        assert github_tokens.resolve_token(db, client.alice.id)[1] != "user"

    put(client, github_token="tok_priya")
    assert put(client, github_username="octocat").json() | {"others": []} == {
        "github_username": "octocat", "github_token_saved": False, "linkedin": None,
        "website": None, "portfolio": None, "others": [], "from_resume": False,
    }


def test_pow_refresh_uses_the_saved_username_without_a_token(client):
    client.post("/v1/me/consents", json=consent(github=True))
    assert client.post("/v1/profile/pow/refresh").status_code == 422
    put(client, github_username="octocat")
    resp = client.post("/v1/profile/pow/refresh")
    assert resp.status_code == 202, resp.text
    assert resp.json()["github_username"] == "octocat"


def test_presence_is_private_to_the_account(client):
    put(client, website="priya.dev")
    login_as(client, client.bob)
    assert client.get("/v1/me/online-presence").json()["website"] is None


def _resume_link(client, url, status="approved"):
    from app.facts.models import ProfileFact

    with app_db(client) as db:
        db.add(ProfileFact(account_id=client.alice.id, kind="link", text=url, structured={"url": url},
                           source="resume", status=status))
        db.commit()


def test_nothing_saved_yet_prefills_from_resume_links(client):
    for url in ("https://www.linkedin.com/in/priya-sharma", "github.com/priyadev", "https://priya.dev",
                "https://www.behance.net/priya", "https://leetcode.com/u/priya"):
        _resume_link(client, url)
    _resume_link(client, "https://ignored.example.com", status="proposed")  # never approved

    body = client.get("/v1/me/online-presence").json()
    assert body["from_resume"] is True
    assert body["github_username"] == "priyadev"
    assert body["linkedin"] == "https://www.linkedin.com/in/priya-sharma"
    assert body["website"] == "https://priya.dev"
    assert body["portfolio"] == "https://www.behance.net/priya"
    assert body["others"] == [{"label": "Leetcode", "url": "https://leetcode.com/u/priya"}]


def test_saving_retires_the_resume_copy_of_the_same_link(client):
    _resume_link(client, "https://www.linkedin.com/in/priya-sharma/")
    _resume_link(client, "https://priya.dev")
    put(client, linkedin="linkedin.com/in/priya-sharma")
    links = client.get("/v1/profile").json()["profile"]["identity"]["links"]
    assert sorted(l["url"] for l in links) == ["https://linkedin.com/in/priya-sharma", "https://priya.dev"]
    assert client.get("/v1/me/online-presence").json()["from_resume"] is False


def test_resume_sentences_with_trailing_dots_still_prefill_and_dedupe(client):
    from app.facts.models import ProfileFact

    with app_db(client) as db:
        for text in ("GitHub: github.com/octocat.", "LinkedIn: linkedin.com/in/aarav-mehta-dev."):
            db.add(ProfileFact(account_id=client.alice.id, kind="link", text=text, structured={},
                               source="resume", status="approved"))
        db.commit()
    body = client.get("/v1/me/online-presence").json()
    assert body["github_username"] == "octocat"
    assert body["linkedin"] == "https://linkedin.com/in/aarav-mehta-dev"
    put(client, github_username="octocat", linkedin=body["linkedin"])
    links = client.get("/v1/profile").json()["profile"]["identity"]["links"]
    assert sorted(l["url"] for l in links) == ["https://github.com/octocat", "https://linkedin.com/in/aarav-mehta-dev"]
