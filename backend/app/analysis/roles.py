from typing import Optional


def project_role(
    username: str, owner_login: str, authored_commits: int, contributors: list[dict]
) -> tuple[str, Optional[float]]:
    """Role in a repo from the user's share of all commits (GitHub contributors stats)."""
    total = sum(c.get("contributions", 0) for c in contributors)
    user_commits = next(
        (c.get("contributions", 0) for c in contributors if (c.get("login") or "").lower() == username.lower()),
        authored_commits,
    )
    share = min(user_commits / total, 1.0) if total else (1.0 if authored_commits else None)
    is_owner = owner_login.lower() == username.lower()

    if share is None:
        return "Contributor", None
    if is_owner and share >= 0.7:
        role = "Primary author"
    elif share >= 0.5:
        role = "Lead contributor"
    elif share >= 0.15:
        role = "Core contributor"
    else:
        role = "Contributor"
    return role, round(share, 3)
