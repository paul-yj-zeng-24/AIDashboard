"""
cli.py — chat in the terminal using the SAME agent as the web page.

Run: `uv run python cli.py`

This shows why the layers are separate: agent.reply() doesn't care whether
the conversation comes from a web page, the terminal, or (later) an email
inbox. Each is just a different front-end calling the same function.
"""
from app import agent

# Here the terminal program keeps the conversation (in the web version the
# browser does). Each turn we append to it and pass the whole thing in.
history = []
print("AI Dashboard chat. /quit to exit.\n")

while True:
    try:
        user = input("you> ").strip()
    except (EOFError, KeyboardInterrupt):   # Ctrl-D / Ctrl-C exits cleanly
        break
    if user in {"/quit", "/exit"}:
        break
    if not user:
        continue

    history.append({"role": "user", "content": user})
    answer = agent.reply(history)                       # may call tools internally
    history.append({"role": "assistant", "content": answer})
    print(f"ai>  {answer}\n")
