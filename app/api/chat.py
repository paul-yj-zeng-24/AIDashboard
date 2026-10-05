"""
chat.py: the chat endpoints.

  POST /api/chat                          send a message, get a streamed reply
  GET  /api/conversations                 the sidebar list
  GET  /api/conversations/{id}/messages   one thread's messages

How streaming reaches the browser: Server-Sent Events (SSE). Instead of one
JSON response, the server keeps the connection open and writes lines like

    data: {"type": "text", "delta": "It's 64"}\n\n

as events happen. Each `data:` line followed by a blank line is one event.
The page reads them as they arrive (see static/index.html).
"""
import json
from typing import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import select

from app.agent import loop
from app.db.models import Conversation, Message
from app.db.session import new_session

router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None  # None = start a new conversation


def sse(events: Iterator[dict]) -> Iterator[str]:
    """Format each event dict as one Server-Sent Events message."""
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Empty message")
    # StreamingResponse pulls from the generator and sends each piece as soon
    # as it's yielded. Because run_turn is a normal (not async) generator,
    # FastAPI runs it in a background thread, so a slow model doesn't block
    # other requests.
    return StreamingResponse(
        sse(loop.run_turn(req.conversation_id, req.message)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/conversations")
def list_conversations(limit: int = 50):
    with new_session() as session:
        rows = session.exec(
            select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
        ).all()
        return [{"id": c.id, "title": c.title, "updated_at": c.updated_at} for c in rows]


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int):
    with new_session() as session:
        if session.get(Conversation, conversation_id) is None:
            raise HTTPException(404, "No such conversation")
        rows = session.exec(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        ).all()
        return [{"role": m.role, "content": m.content, "run_id": m.run_id, "created_at": m.created_at}
                for m in rows]
