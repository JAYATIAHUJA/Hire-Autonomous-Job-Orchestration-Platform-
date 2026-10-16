"""GitHub and Google OAuth (authorization-code flow) - the HTTP half.

Each provider turns a callback ``code`` into a ``ProviderUser``. Tests replace
``http_client`` with one built on ``httpx.MockTransport``, so nothing reaches the network.
"""

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx

from ..config import settings

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
# Public profile and verified emails only. Private repos are never analysed (B8).
GITHUB_SCOPES = "read:user user:email"

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_SCOPES = "openid email profile"


class OAuthError(RuntimeError):
    """The provider refused the code or returned something we can't use."""


class OAuthNotConfigured(RuntimeError):
    """Client id/secret for this provider are not set."""


@dataclass(frozen=True)
class ProviderUser:
    provider: str
    subject: str
    email: Optional[str]
    email_verified: bool
    display_name: Optional[str]
    username: Optional[str] = None
    access_token: Optional[str] = None


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15)


def callback_url(provider: str) -> str:
    return settings.auth_callback_base_url.rstrip("/") + f"/v1/auth/{provider}/callback"


def _credentials(provider: str) -> tuple[str, str]:
    cid = getattr(settings, f"{provider}_oauth_client_id")
    secret = getattr(settings, f"{provider}_oauth_client_secret")
    if not (cid and secret):
        name = provider.upper()
        raise OAuthNotConfigured(f"{name}_OAUTH_CLIENT_ID and {name}_OAUTH_CLIENT_SECRET are not set.")
    return cid, secret


def authorize_url(provider: str, state: str) -> str:
    client_id, _ = _credentials(provider)
    if provider == "github":
        params = {"client_id": client_id, "redirect_uri": callback_url("github"), "scope": GITHUB_SCOPES,
                  "state": state, "allow_signup": "true"}
        return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"
    params = {"client_id": client_id, "redirect_uri": callback_url("google"), "response_type": "code",
              "scope": GOOGLE_SCOPES, "state": state, "prompt": "select_account"}
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


async def github_user(code: str) -> ProviderUser:
    client_id, secret = _credentials("github")
    async with http_client() as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={"client_id": client_id, "client_secret": secret, "code": code,
                  "redirect_uri": callback_url("github")},
            headers={"Accept": "application/json"},
        )
        token = resp.json().get("access_token") if resp.status_code == 200 else None
        if not token:
            raise OAuthError("GitHub did not accept the login code.")

        auth = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        api = settings.github_api_base.rstrip("/")
        user_resp = await client.get(f"{api}/user", headers=auth)
        if user_resp.status_code != 200:
            raise OAuthError("Could not read the GitHub profile.")
        user = user_resp.json()

        email, verified = None, False
        emails_resp = await client.get(f"{api}/user/emails", headers=auth)
        if emails_resp.status_code == 200:
            for entry in emails_resp.json():
                if entry.get("primary") and entry.get("verified"):
                    email, verified = entry.get("email"), True
                    break

    return ProviderUser(
        provider="github",
        subject=str(user["id"]),
        email=email,
        email_verified=verified,
        display_name=user.get("name") or user.get("login"),
        username=user.get("login"),
        access_token=token,
    )


async def google_user(code: str) -> ProviderUser:
    client_id, secret = _credentials("google")
    async with http_client() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={"client_id": client_id, "client_secret": secret, "code": code,
                  "grant_type": "authorization_code", "redirect_uri": callback_url("google")},
        )
        token = resp.json().get("access_token") if resp.status_code == 200 else None
        if not token:
            raise OAuthError("Google did not accept the login code.")

        info_resp = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {token}"})
        if info_resp.status_code != 200:
            raise OAuthError("Could not read the Google profile.")
        info = info_resp.json()

    if not info.get("sub"):
        raise OAuthError("Google returned no account id.")
    # We don't keep the Google token: login needs nothing beyond the identity.
    return ProviderUser(
        provider="google",
        subject=str(info["sub"]),
        email=info.get("email"),
        email_verified=info.get("email_verified") is True,
        display_name=info.get("name"),
    )
