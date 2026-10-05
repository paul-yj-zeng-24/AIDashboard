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
from typing import AsyncIterator, Generator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import select
from starlette.concurrency import iterate_in_threadpool

from app.agent import loop
from app.db.models import Conversation, Message
from app.db.session import new_session

router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None  # None = start a new conversation


async def sse(events: Generator[dict, None, None]) -> AsyncIterator[str]:
    """Format each event dict as one Server-Sent Events message.

    run_turn is a normal (not async) generator whose steps can be slow (a
    model call takes seconds). iterate_in_threadpool runs each step in a
    background thread, so a slow model doesn't block other requests.

    The `finally` matters when the browser disconnects mid-reply. The server
    then stops reading from us, but it does NOT close run_turn: that would
    only happen whenever Python's garbage collector got round to it, and
    until then the reply and its trace stay unsaved. Closing it ourselves
    runs run_turn's own `finally` (which saves them) right away.
    """
    try:
        async for event in iterate_in_threadpool(events):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    finally:
        events.close()


@router.post("/chat")
def chat(req: ChatRequest):
    # A plain `def` (not `async def`): the existence check below is a
    # blocking database call, and FastAPI runs `def` routes in a background
    # thread so the server never waits on it.
    if not req.message.strip():
        raise HTTPException(400, "Empty message")
    # Refuse an unknown conversation BEFORE streaming starts, so nothing is
    # written and the page gets a plain 404 it can react to.
    if req.conversation_id is not None and not loop.conversation_exists(req.conversation_id):
        raise HTTPException(404, "No such conversation")
    # StreamingResponse pulls from sse() and sends each piece as soon as it's
    # yielded.
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
