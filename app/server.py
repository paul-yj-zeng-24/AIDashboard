"""
server.py — the web layer. It serves the chat page and exposes one API
endpoint. No AI logic lives here; it just passes messages to agent.py.

How it runs: `uv run uvicorn app.server:app --reload`
  - uvicorn is the web server program; it listens on http://localhost:8000
  - "app.server:app" means: in the module app/server.py, use the variable `app`
  - --reload restarts the server whenever you save a .py file

The server is STATELESS: it remembers nothing between requests. The browser
keeps the conversation and sends all of it with each message (the LLM API
needs the full conversation anyway, see llm.py). Upside: simple, and a
restart loses nothing. Downside: refreshing the page clears the chat.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app import agent

# Absolute path to the static/ folder, computed from this file's location so
# it works no matter which directory you start the server from.
STATIC = Path(__file__).resolve().parent.parent / "static"

# The FastAPI application. The decorators below (@app.get / @app.post)
# register functions to handle requests to specific URLs.
app = FastAPI()


# Describes the JSON body the browser sends to /api/chat:
#   {"messages": [{"role": "user", "content": "hi"}, ...]}
# FastAPI checks incoming requests against this and rejects malformed ones
# with a 422 error automatically.
class ChatRequest(BaseModel):
    messages: list[dict]


# Visiting http://localhost:8000/ in the browser -> send back the chat page.
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


# The page's JavaScript POSTs here each time you send a message.
# Note this is a plain `def`, not `async def`: FastAPI then runs it in a
# background thread, so a slow model call doesn't freeze the whole server.
@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        return {"reply": agent.reply(req.messages)}   # -> {"reply": "..."}
    except Exception as e:
        # Missing API key, network error, provider error, etc. Send the
        # message to the page so you see what went wrong instead of a
        # generic "500 Internal Server Error".
        return JSONResponse({"error": str(e)}, status_code=500)
