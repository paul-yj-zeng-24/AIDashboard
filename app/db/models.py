"""
models.py: the database tables, written as Python classes.

SQLModel lets one class be two things at once:
  - a Pydantic model (validated Python object you can turn into JSON), and
  - a SQL table (each attribute = a column, each object = a row).

So `Message(role="user", content="hi")` is a normal Python object, and
`session.add(msg); session.commit()` saves it as a row in data/app.db.

Phase 1 needs three tables:
  Conversation  one chat thread (the sidebar entries)
  Message       one visible message in a thread (user or assistant text)
  Trace         one step inside a turn: a model call or a tool call

Note on changing these later: SQLModel creates missing tables on startup but
does NOT alter existing ones. If you add a column while developing, delete
data/app.db (you lose old chats) or add a migration tool such as Alembic.
"""
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    # Store times in UTC; convert to local time only when displaying.
    return datetime.now(timezone.utc)


class Conversation(SQLModel, table=True):
    # `int | None = None` + primary_key: the database assigns the id on insert.
    id: int | None = Field(default=None, primary_key=True)
    title: str = ""  # first words of the first message, shown in the sidebar
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # foreign_key links each message to its conversation; index=True makes
    # "all messages of conversation 7" a fast lookup.
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    role: str  # "user" or "assistant"
    content: str
    # The agent run (turn) this message belongs to: the question and its reply
    # share one run_id, which also links them to their traces.
    run_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Trace(SQLModel, table=True):
    """One logged step. A single user message ("what's the weather?") usually
    creates 3 rows: model call -> tool call -> model call."""
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)  # groups the steps of one turn
    conversation_id: int | None = Field(default=None, index=True)
    step: int  # which model round inside the turn (0, 1, 2, ...)
    kind: str  # "model" or "tool"
    name: str  # model id, or tool name
    input: str  # what went in (JSON text)
    output: str  # what came out (JSON text)
    tokens_in: int | None = None  # only for model calls, if the provider reports it
    tokens_out: int | None = None
    latency_ms: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
