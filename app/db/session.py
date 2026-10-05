"""
session.py: the connection to the SQLite database file.

Two ideas:
  engine   one object per app that knows where the database is (data/app.db).
  Session  a short-lived "conversation" with the database. Open one, read or
           add rows, commit, close. Use it as `with Session(engine) as s: ...`
           so it closes itself even if an error happens.
"""
from sqlmodel import Session, SQLModel, create_engine

from app import config
from app.db import models  # noqa: F401  (imported so its tables get registered)

config.DATA_DIR.mkdir(parents=True, exist_ok=True)

# check_same_thread=False: FastAPI handles requests on several threads, and
# SQLite's Python driver refuses that by default. It's safe here because each
# request opens its own Session.
engine = create_engine(
    f"sqlite:///{config.DB_PATH}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create any tables that don't exist yet. Called once at startup."""
    SQLModel.metadata.create_all(engine)


def new_session() -> Session:
    return Session(engine)
