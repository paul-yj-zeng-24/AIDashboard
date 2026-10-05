"""
tools.py — functions the model can ask us to run.

This is how an LLM goes from "text predictor" to "agent". The model can't
access your calendar or the internet; it can only produce text. So we:

  1. DESCRIBE each function to the model (name, purpose, arguments) as JSON.
  2. The model, when useful, replies with a structured request instead of
     text: "call get_current_time with {"timezone": "Asia/Shanghai"}".
  3. OUR code (agent.py) runs the real Python function and sends the result
     back to the model as a new message.

The model never executes anything. It only asks; your code decides and runs.
That boundary is also where safety lives later: e.g. "read calendar" can run
automatically, while "send email" should wait for your approval.

This file is where the dashboard grows: calendar, Gmail, Notion and weather
each become a function + an entry in TOOLS below.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# 1) The actual Python functions. Plain code; nothing AI-specific here.
#    Return a string (or something str() works on): the model reads text.
# ---------------------------------------------------------------------------

def get_current_time(timezone: str = "America/Los_Angeles") -> str:
    # LLMs don't know the current time (their knowledge is frozen at
    # training), which makes this a good first tool.
    return datetime.now(ZoneInfo(timezone)).strftime("%A %Y-%m-%d %H:%M %Z")


# ---------------------------------------------------------------------------
# 2) The registry: maps each tool's name to its function and its description.
#    The model never sees the Python code, only "description" and
#    "parameters". Write these clearly: they are effectively part of the
#    prompt, and vague descriptions make the model use tools badly.
#
#    "parameters" is JSON Schema: the standard way to describe the shape of
#    a JSON object (which keys, what types, which are required).
# ---------------------------------------------------------------------------

TOOLS = {
    "get_current_time": {
        "fn": get_current_time,
        "description": "Get the current date and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "description": "IANA name, e.g. Asia/Shanghai"},
            },
            # No "required" list, so the model may omit timezone and the
            # Python default (America/Los_Angeles) is used.
        },
    },
    # To add a tool, add another entry here, e.g.
    # "get_weather": {"fn": get_weather, "description": "...", "parameters": {...}},
}


# ---------------------------------------------------------------------------
# 3) Helpers used by agent.py
# ---------------------------------------------------------------------------

def schemas() -> list[dict]:
    """Convert TOOLS into the exact format the chat completions API expects:
    [{"type": "function", "function": {"name", "description", "parameters"}}, ...]
    (We drop "fn": the model only gets the description, never the code.)"""
    return [
        {"type": "function", "function": {"name": name, "description": t["description"], "parameters": t["parameters"]}}
        for name, t in TOOLS.items()
    ]


def run(name: str, arguments_json: str) -> str:
    """Execute one tool request from the model.

    name:            which tool the model asked for, e.g. "get_current_time"
    arguments_json:  the arguments, as a JSON *string* the model generated,
                     e.g. '{"timezone": "Asia/Shanghai"}'

    If anything goes wrong (unknown tool, bad arguments, the function itself
    fails) we return the error as text instead of crashing. The error goes
    back to the model, which usually fixes its mistake on the next try.
    """
    try:
        args = json.loads(arguments_json or "{}")   # JSON string -> Python dict
        return str(TOOLS[name]["fn"](**args))       # **args: dict -> keyword args
    except Exception as e:
        return f"Error running {name}: {e}"
