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

    # With a token GitHub allows 5,000 requests/hour; without, 60.
    full_max_repos: int = 20
    full_commits_per_repo: int = 40
    full_external_prs: int = 30
    limited_max_repos: int = 3
    limited_commits_per_repo: int = 8
    limited_external_prs: int = 5

    cors_origins: list[str] = ["*"]

    # Signs the consent receipt written on every swipe right. Override in production:
    # rotating this secret invalidates verification of receipts signed before it.
    consent_signing_secret: str = "hire-unplug-dev-consent-secret"

    # Background recruiter-mailbox reader. Disabled by default so local runs and
    # tests never reach for a mailbox; the /api/mail/sync endpoint works either way.
    imap_enabled: bool = False
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    imap_search: str = "UNSEEN"
    imap_poll_seconds: int = 300
    imap_fetch_limit: int = 25

    def limits(self, has_token: bool) -> AnalysisLimits:
        if has_token:
            return AnalysisLimits("full", self.full_max_repos, self.full_commits_per_repo, self.full_external_prs)
        return AnalysisLimits(
            "limited", self.limited_max_repos, self.limited_commits_per_repo, self.limited_external_prs
        )


settings = Settings()
