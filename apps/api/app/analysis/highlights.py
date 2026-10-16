import re

from .contribution import Contribution


def _title_key(c: Contribution) -> tuple[str, str]:
    return c.repo, re.sub(r"[^a-z ]", "", c.title.lower())[:40].strip()


def top_contributions(contributions: list[Contribution], limit: int = 5) -> list[Contribution]:
    """Strongest distinct pieces of work; bulk imports only if nothing better exists."""
    ranked = sorted(contributions, key=lambda c: (c.bulk, -c.weight))
    picked, seen = [], set()
    for c in ranked:
        key = _title_key(c)
        if key in seen or c.weight <= 0:
            continue
        seen.add(key)
        picked.append(c)
        if len(picked) == limit:
            break
    return picked
