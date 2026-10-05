"""
Tests that need a REAL running server, not FastAPI's TestClient.

Why: some bugs only show up when a browser actually disconnects. TestClient
reads every response to the end, so it can never "close the tab" halfway
through a streamed reply. Here we start uvicorn in a background thread on a
free port and talk to it over a real TCP connection.
"""
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from sqlmodel import select

from app.agent import llm
from app.agent.llm import ModelReply, TextDelta
from app.db.models import Message, Trace
from app.db.session import new_session
from app.main import app


@pytest.fixture
def live_server():
    """Run the app on 127.0.0.1:<free port> for the duration of one test."""
    with socket.socket() as s:      # ask the OS for a free port
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        assert time.monotonic() < deadline, "server didn't start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(5)


def slow_model(messages, tools=None, model=None):
    """A fake model that writes one word every 0.3 s, like a slow provider."""
    words = ["Half ", "a ", "reply ", "that ", "never ", "finishes ", "in ", "time "]
    for word in words:
        yield TextDelta(word)
        time.sleep(0.3)
    yield ModelReply("".join(words))


def poll(check, seconds=2.0):
    """Retry `check` until it returns something truthy or time runs out."""
    deadline = time.monotonic() + seconds
    while True:
        result = check()
        if result or time.monotonic() > deadline:
            return result
        time.sleep(0.05)


def test_browser_disconnect_saves_partial_reply(live_server, monkeypatch):
    monkeypatch.setattr(llm, "stream", slow_model)

    # trust_env=False: ignore any HTTP proxy settings and connect directly.
    with httpx.Client(timeout=5, trust_env=False) as client:
        with client.stream("POST", live_server + "/api/chat", json={"message": "hi"}) as response:
            for line in response.iter_lines():
                if line.startswith("data: ") and json.loads(line[6:])["type"] == "text":
                    break  # got the first word: now "close the tab"
    # Leaving both `with` blocks closed the connection mid-reply.

    # Check the database directly. (Another HTTP request could make Python
    # clean up the abandoned reply by accident and hide the bug.)
    def saved():
        with new_session() as s:
            reply = s.exec(select(Message).where(Message.role == "assistant")).first()
            trace = s.exec(select(Trace).where(Trace.error.startswith("cancelled"))).first()
            return (reply.content, trace.kind) if reply and trace else None

    result = poll(saved)
    assert result is not None, "partial reply and cancelled trace were not saved within 2 s"
    content, kind = result
    assert content.startswith("Half") and kind == "model"
