"""The HTTP layer: streaming chat over SSE, conversation list, trace endpoints."""
import json

from fastapi.testclient import TestClient
from sqlmodel import select

from app.agent.llm import ModelReply, TextDelta, ToolCall
from app.db.models import Conversation, Message
from app.db.session import new_session
from app.main import app

# TestClient sends "Host: testserver" by default, which the server rightly
# refuses. Use localhost, the real default in ALLOWED_HOSTS.
client = TestClient(app, base_url="http://localhost")


def read_sse(response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.split("\n\n") if line.startswith("data: ")]


def test_chat_streams_events_and_lists_conversation(fake_llm):
    fake_llm([
        [ModelReply("", [ToolCall("c1", "get_current_time", "{}")])],
        [TextDelta("Noon."), ModelReply("Noon.")],
    ])
    response = client.post("/api/chat", json={"message": "What time is it?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = read_sse(response)
    assert [e["type"] for e in events] == ["conversation", "tool_start", "tool_end", "text", "done"]

    conversation_id, run_id = events[0]["id"], events[-1]["run_id"]
    convs = client.get("/api/conversations").json()
    assert convs[0]["id"] == conversation_id and convs[0]["title"] == "What time is it?"

    msgs = client.get(f"/api/conversations/{conversation_id}/messages").json()
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "What time is it?"), ("assistant", "Noon.")]

    runs = client.get("/api/runs").json()
    assert runs[0]["run_id"] == run_id
    assert runs[0]["steps"] == 3 and runs[0]["tools"] == ["get_current_time"]
    assert runs[0]["question"] == "What time is it?" and runs[0]["errors"] == 0

    steps = client.get(f"/api/runs/{run_id}").json()
    assert [s["kind"] for s in steps] == ["model", "tool", "model"]


def test_unknown_conversation_is_404_and_writes_nothing(fake_llm):
    """E.g. a tab still open after data/app.db was deleted. The server must
    refuse, not silently start a new thread on every message."""
    fake_llm([[TextDelta("hi"), ModelReply("hi")]])  # in case the model is (wrongly) called
    response = client.post("/api/chat", json={"message": "hello?", "conversation_id": 999})
    assert response.status_code == 404
    with new_session() as s:
        assert s.exec(select(Conversation)).all() == []
        assert s.exec(select(Message)).all() == []


def test_foreign_host_is_rejected():
    """DNS rebinding: a web page can point its own domain at 127.0.0.1, and
    the browser then sends that domain as the Host header. Only the names in
    ALLOWED_HOSTS may read chats and traces."""
    foreign = TestClient(app, base_url="http://evil.example.com")
    assert foreign.get("/api/runs").status_code == 400
    assert client.get("/api/runs").status_code == 200  # Host: localhost


def test_empty_message_rejected():
    assert client.post("/api/chat", json={"message": "   "}).status_code == 400


def test_missing_things_are_404():
    assert client.get("/api/conversations/999/messages").status_code == 404
    assert client.get("/api/runs/nope").status_code == 404


def test_pages_are_served():
    with TestClient(app, base_url="http://localhost") as c:  # `with` runs startup (init_db), like the real server
        assert "AI Dashboard" in c.get("/").text
        assert "Trace view" in c.get("/traces").text
