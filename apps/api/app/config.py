from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class AnalysisLimits:
    mode: str
    max_repos: int
    commits_per_repo: int
    external_prs: int


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "sqlite:///./hire.db"
    github_api_base: str = "https://api.github.com"
    github_concurrency: int = 8
    max_commits_listed_per_repo: int = 300
    # Server-side token used for background PoW runs when the user has not linked
    # GitHub. Empty means unauthenticated (60 requests/hour, no GraphQL totals).
    github_app_token: str = ""
    # Waits shorter than this (Retry-After / X-RateLimit-Reset) are slept through;
    # longer ones fail the request as rate-limited.
    github_max_retries: int = 3
    github_max_backoff_seconds: float = 60.0
    github_etag_cache_size: int = 4096

    # Proof-of-Work background runs (python -m app.worker picks them up).
    pow_poll_seconds: float = 2.0
    # A run still "running" after this long is presumed dead (worker crash) and failed.
    pow_stale_run_seconds: int = 1800

    # With a token GitHub allows 5,000 requests/hour; without, 60.
    full_max_repos: int = 20
    full_commits_per_repo: int = 40
    full_external_prs: int = 30
    limited_max_repos: int = 3
    limited_commits_per_repo: int = 8
    limited_external_prs: int = 5

    cors_origins: list[str] = ["*"]

    # Signs the consent receipt written on every swipe right. There is no default:
    # a known secret lets anyone forge receipts. Rotating it invalidates verification
    # of receipts signed before it.
    consent_signing_secret: str = ""

    # Live job feeds (RemoteOK). Tests turn this off so they never touch the network.
    live_feeds_enabled: bool = True

    # Background worker (python -m app.worker).
    discovery_interval_seconds: int = 1800
    discovery_batch_size: int = 50

    # Background recruiter-mailbox reader. Disabled by default so local runs and
    # tests never reach for a mailbox; the /api/mail/sync endpoint works either way.
    imap_enabled: bool = False
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    imap_candidate_ref: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    imap_search: str = "UNSEEN"
    imap_poll_seconds: int = 300
    imap_fetch_limit: int = 25

    # --- Accounts and sessions (WP1, ADR-010) ---
    # "dev" turns on POST /v1/auth/dev-login and prints OTP codes to the console.
    # Anything else is treated as production.
    env: str = "prod"
    session_cookie_name: str = "hire_session"
    session_ttl_days: int = 30
    # Browsers treat http://localhost as a secure context, so this stays on in dev too.
    session_cookie_secure: bool = True
    # Fernet key that encrypts stored OAuth tokens. Required for GitHub login.
    token_encryption_key: str = ""
    # Where OAuth providers send the browser back to (this API, or the web app's proxy to it).
    auth_callback_base_url: str = "http://localhost:8100"
    # Where the browser lands after an OAuth login.
    web_app_url: str = "http://localhost:5173"
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    # Accounts with these (verified) emails get the admin role.
    admin_emails: list[str] = []
    # OTP mail: "console" or "smtp". Empty picks console when ENV=dev, else smtp.
    otp_sender: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    # Object store (ADR-009): SeaweedFS in dev, AWS S3 in prod. S3 API only.
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "ap-south-1"

    # Anthropic (app/llm). The model id lives here only; call sites never name a model.
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "medium"
    llm_max_tokens: int = 16000
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 3
    # Server-side refusal fallback (beta). Turn off if a proxy rejects the field.
    llm_refusal_fallback: bool = True

    def limits(self, has_token: bool) -> AnalysisLimits:
        if has_token:
            return AnalysisLimits("full", self.full_max_repos, self.full_commits_per_repo, self.full_external_prs)
        return AnalysisLimits(
            "limited", self.limited_max_repos, self.limited_commits_per_repo, self.limited_external_prs
        )


settings = Settings()
