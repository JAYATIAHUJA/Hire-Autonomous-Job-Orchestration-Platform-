from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "sqlite:///./hire.db"
    github_api_base: str = "https://api.github.com"
    max_repos_per_user: int = 20
    max_commits_per_repo: int = 300
    commit_stats_sample_size: int = 10
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
