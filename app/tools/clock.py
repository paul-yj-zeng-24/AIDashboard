"""Time tools. The system prompt already states Paul's local time, so this
mostly matters for other time zones ("what time is it in Shanghai?")."""
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import Field

from app import config
from app.tools.registry import Tier, tool


@tool(tier=Tier.READ)
def get_current_time(
    timezone: Annotated[str | None, Field(description="IANA time zone, e.g. Asia/Shanghai. Omit for Paul's local time.")] = None,
) -> str:
    """Get the current date and time in a time zone."""
    return datetime.now(ZoneInfo(timezone or config.TIMEZONE)).strftime("%A %Y-%m-%d %H:%M %Z")
