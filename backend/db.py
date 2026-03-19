import os
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# In-memory for tests; override with DATABASE_URL in production
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://claude:claude@localhost:5432/claude_usage",  # default for local dev; overridden by DATABASE_URL env var
)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    engine = create_engine(DATABASE_URL, connect_args=connect_args, poolclass=StaticPool)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_db() -> bool:
    """Return True if DB is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
