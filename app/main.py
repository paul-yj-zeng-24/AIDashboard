"""
main.py: creates the web app and wires the pieces together.

Run it with:   uv run uvicorn app.main:app --reload
  - uvicorn is the web server program; it listens on http://localhost:8000
  - "app.main:app" means: in the module app/main.py, use the variable `app`
  - --reload restarts the server whenever you save a .py file

Pages:   /         the chat
         /traces   what the agent did, step by step
APIs:    /api/...  see app/api/  (FastAPI also shows them all at /docs)
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import config
from app.api import chat, traces
from app.db.session import init_db

STATIC = Path(__file__).resolve().parent.parent / "static"


# "lifespan" = code that runs once when the server starts (before `yield`)
# and once when it stops (after `yield`).
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # create the database tables if they don't exist yet
    yield


app = FastAPI(title="AI Dashboard", lifespan=lifespan)
# Middleware = code that runs on every request before any route sees it.
# This one answers 400 to any request whose Host header isn't in
# ALLOWED_HOSTS (see config.py for why).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)
app.include_router(chat.router)
app.include_router(traces.router)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/traces", include_in_schema=False)
def traces_page():
    return FileResponse(STATIC / "traces.html")
