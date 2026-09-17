"""Database access for profiles — the only module that talks to a ``Session``."""

from typing import Optional

from sqlalchemy.orm import Session, selectinload

from .. import models


def save(db: Session, user: models.User) -> models.User:
    """Persist a freshly built profile graph and return it with its generated id."""
    db.add(user)
    db.commit()
    return user


def load(db: Session, profile_id: int) -> Optional[models.User]:
    """Load a profile with every relationship the serializer needs, in one round of queries."""
    return (
        db.query(models.User)
        .options(
            selectinload(models.User.projects),
            selectinload(models.User.contributions),
            selectinload(models.User.skills).selectinload(models.Skill.highlights),
        )
        .filter(models.User.id == profile_id)
        .first()
    )
