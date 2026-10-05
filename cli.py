"""
cli.py: chat in the terminal using the SAME agent loop as the web page.

Run: `uv run python cli.py`            start a new conversation
     `uv run python cli.py 7`          continue conversation 7 (ids are in the sidebar URL)

It shows why the layers are separate: run_turn() only yields events. The web
page turns them into bubbles; this file turns them into printed text.
"""
import sys

from app.agent.loop import run_turn
from app.db.session import init_db

init_db()
conversation_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
print("AI Dashboard chat. /quit to exit.\n")

while True:
    try:
        user = input("you> ").strip()
    except (EOFError, KeyboardInterrupt):  # Ctrl-D / Ctrl-C exits cleanly
        break
    if user in {"/quit", "/exit"}:
        break
    if not user:
        continue

    print("ai>  ", end="", flush=True)
    for event in run_turn(conversation_id, user):
        kind = event["type"]
        if kind == "conversation":
            conversation_id = event["id"]          # keep talking in the same thread
        elif kind == "text":
            print(event["delta"], end="", flush=True)  # flush = show it right away
        elif kind == "tool_start":
            print(f"\n     [using {event['name']} {event['arguments']}]", end="", flush=True)
        elif kind == "tool_end":
            print(" ok" if event["ok"] else " failed", end="\n     ", flush=True)
        elif kind == "error":
            print(f"\n     [error] {event['message']}", end="")
        elif kind == "done":
            print(f"\n     (trace: /traces#run={event['run_id']})\n")
