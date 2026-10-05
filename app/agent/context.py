"""
context.py: builds what the model needs to know at the start of every turn.

The model remembers nothing between calls, so each turn we rebuild its
"briefing" from fixed pieces:

  1. the rules         agent/prompts/system.md (edit it like any text file)
  2. right now         the current date/time and where Paul lives
  3. about Paul        data/profile.md, if you've written one (see profile.example.md)
  4. the conversation  the last HISTORY_LIMIT messages from the database

Later phases add a "today snapshot" (next events, what's due) here, so
simple questions don't even need a tool call.
"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlmodel import select

from app import config
from app.db.models import Message
from app.db.session import new_session

PROMPTS_DIR = Path(__file__).parent / "prompts"


def system_prompt() -> str:
    parts = [(PROMPTS_DIR / "system.md").read_text()]

    now = datetime.now(ZoneInfo(config.TIMEZONE))
    parts.append(f"Current time: {now:%A %Y-%m-%d %H:%M} ({config.TIMEZONE}).\n"
                 f"Paul's home: {config.HOME_NAME}.")

    if config.PROFILE_PATH.exists():
        parts.append("About Paul (written by him):\n" + config.PROFILE_PATH.read_text())

    return "\n\n".join(parts)


def history(conversation_id: int) -> list[dict]:
    """The most recent messages of a conversation, oldest first, in API format."""
    with new_session() as session:
        rows = session.exec(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())   # newest first, so .limit() keeps the latest...
            .limit(config.HISTORY_LIMIT)
        ).all()
    # ...then flip back to oldest-first, the order the model expects.
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def build_messages(conversation_id: int) -> list[dict]:
    return [{"role": "system", "content": system_prompt()}, *history(conversation_id)]
