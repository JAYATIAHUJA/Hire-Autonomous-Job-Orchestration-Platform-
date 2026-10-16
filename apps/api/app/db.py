from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create tables for local SQLite runs. Postgres schemas come only from Alembic
    (``alembic upgrade head``), so a missing migration fails loudly instead of being
    papered over by create_all."""
    if not settings.database_url.startswith("sqlite"):
        return

    from . import models  # noqa: F401  (registers tables on Base.metadata)
    from .jobs import models as job_models  # noqa: F401
    from .applications import models as application_models  # noqa: F401
    from .auth import models as auth_models  # noqa: F401
    from .profiles import pow_models  # noqa: F401
    from .facts import models as fact_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
