"""
loop.py: the agent loop, now with streaming, memory and tracing.

The core is the same loop as Phase 0:

    while True:
        ask the model what to do next
        if it gives a final text answer   -> done
        if it asks to use tools           -> run them, show it the results, repeat

What's new:
  - run_turn() is a GENERATOR. Instead of returning one string at the end, it
    `yield`s small event dicts as things happen, so the page can show text as
    it is written and "using get_weather…" while a tool runs:

        {"type": "conversation", "id": 7}            which thread this turn belongs to
        {"type": "text", "delta": "It's 64"}         a piece of the reply
        {"type": "tool_start", "name": "get_weather", "arguments": "{...}"}
        {"type": "tool_end", "name": "get_weather", "ok": true}
        {"type": "error", "message": "..."}          something broke
        {"type": "done", "run_id": "a1b2c3"}         turn finished

    The web page (via api/chat.py) and the CLI (cli.py) both just loop over
    these events. Neither knows anything about models or tools.

  - Memory: messages are saved in SQLite, and history is loaded from there.
    The browser no longer has to send the whole conversation.

  - Tracing: every model call and tool call is logged (see tracing.py),
    grouped under one run_id per turn.

  - Limits: at most MAX_STEPS model calls per turn. The last one is made
    WITHOUT tools, so the model has to answer with what it has gathered.
"""
import uuid
from dataclasses import asdict
from typing import Iterator

from app import config
from app.agent import context, llm, tracing
from app.agent.tracing import Timer
from app.db.models import Conversation, Message, utcnow
from app.db.session import new_session
from app.tools import registry


def conversation_exists(conversation_id: int) -> bool:
    with new_session() as session:
        return session.get(Conversation, conversation_id) is not None


def run_turn(conversation_id: int | None, user_text: str) -> Iterator[dict]:
    """Handle one user message from start to finish, yielding events.

    conversation_id=None starts a new conversation. An id that doesn't exist
    ends the turn with an error event and saves nothing.
    """
    run_id = uuid.uuid4().hex[:12]  # short random id that groups this turn's traces
    shown: list[str] = []           # every piece of text the user saw, saved at the end
    saved_question = False

    # try/finally: the `finally` block runs however the turn ends: normally,
    # after an error, or when the browser disconnects mid-reply (Python then
    # stops the generator at a `yield`). So the reply is always saved.
    try:
        # 1. Save the user's message first, so it survives even if the model fails.
        conversation_id = _save_message(conversation_id, "user", user_text, run_id=run_id)
        saved_question = True
        yield {"type": "conversation", "id": conversation_id}

        # 2. Build the briefing: system prompt + recent history (incl. the message just saved).
        messages = context.build_messages(conversation_id)
        yield from _agent_rounds(run_id, conversation_id, messages, shown)

    except Exception as e:
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}

    finally:
        # 5. Save what the user saw as the assistant's message, linked to the run.
        # Tool requests/results are NOT saved as messages: they live in the traces.
        # (No `yield` in here: after a disconnect there is nobody to send to.)
        final = "".join(shown).strip()
        if saved_question and final:
            _save_message(conversation_id, "assistant", final, run_id=run_id)

    yield {"type": "done", "run_id": run_id}


def _agent_rounds(run_id: str, conversation_id: int, messages: list[dict],
                  shown: list[str]) -> Iterator[dict]:
    """Steps 3-4: call the model, run the tools it asks for, repeat."""
    tokens_used = 0
    needs_gap = False  # put a blank line between text from different rounds

    for step in range(config.MAX_STEPS):
        last_round = step == config.MAX_STEPS - 1

        # 3. One model call, streamed. On the last round we offer no tools.
        timer = Timer()
        reply = None
        trace = dict(run_id=run_id, conversation_id=conversation_id, step=step,
                     kind="model", name=config.LLM_MODEL_ID, input=messages)
        try:
            for item in llm.stream(messages, tools=None if last_round else registry.schemas()):
                if isinstance(item, llm.TextDelta):
                    text = ("\n\n" + item.text) if needs_gap else item.text
                    needs_gap = False
                    shown.append(text)
                    yield {"type": "text", "delta": text}
                else:
                    reply = item  # the final ModelReply
        except GeneratorExit:
            # The browser went away mid-reply. Log it, then let Python finish stopping us.
            tracing.record(**trace, output="".join(shown), latency_ms=timer.ms(),
                           error="cancelled: the client disconnected")
            raise
        except Exception as e:
            tracing.record(**trace, output="", latency_ms=timer.ms(), error=f"{type(e).__name__}: {e}")
            raise

        # Log exactly what the model saw and what it answered.
        tracing.record(**trace, latency_ms=timer.ms(),
                       output={"content": reply.content, "tool_calls": [asdict(c) for c in reply.tool_calls]},
                       tokens_in=reply.tokens_in, tokens_out=reply.tokens_out)
        tokens_used += (reply.tokens_in or 0) + (reply.tokens_out or 0)

        # 4a. No tool requests: this was the final answer.
        if not reply.tool_calls:
            return
        if last_round:
            # Only happens if a provider sends tool calls although we offered none.
            yield from _note(shown, "(Stopped: too many tool steps.)")
            return

        # 4b. Tool requests. First record the model's request in the working
        # messages (the API requires each tool result to follow it).
        messages.append({
            "role": "assistant",
            "content": reply.content or None,
            "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in reply.tool_calls
            ],
        })
        if reply.content:
            needs_gap = True

        # Then run each tool, log it, and append its result for the model to read.
        for call in reply.tool_calls:
            yield {"type": "tool_start", "name": call.name, "arguments": call.arguments}
            timer = Timer()
            result = registry.run(call.name, call.arguments)
            tracing.record(run_id=run_id, conversation_id=conversation_id, step=step,
                           kind="tool", name=call.name, input=call.arguments,
                           output=result.text, latency_ms=timer.ms(),
                           error=None if result.ok else result.text[:300])
            yield {"type": "tool_end", "name": call.name, "ok": result.ok}
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result.text})

        # Safety valve: too many tokens this turn.
        if tokens_used > config.RUN_TOKEN_BUDGET:
            yield from _note(shown, "(Stopped: this turn used its token budget.)")
            return


def _note(shown: list[str], text: str) -> Iterator[dict]:
    """Show a short system note at the end of the reply."""
    piece = ("\n\n" if shown else "") + text
    shown.append(piece)
    yield {"type": "text", "delta": piece}


class ConversationNotFound(LookupError):
    """A conversation id was given but doesn't exist, for example because
    data/app.db was deleted while a chat tab was still open."""


def _save_message(conversation_id: int | None, role: str, content: str,
                  run_id: str | None = None) -> int:
    """Store one message. Returns its conversation's id.

    conversation_id=None starts a new conversation. An id that doesn't exist
    raises ConversationNotFound instead of quietly starting a new one: the
    caller would keep sending the old id, and every message would land in yet
    another new thread with no history.
    """
    with new_session() as session:
        if conversation_id is None:
            # New thread: title it after the first words of the first message.
            first_line = content.strip().splitlines()[0] if content.strip() else "New chat"
            conversation = Conversation(title=first_line[:60])
            session.add(conversation)
            session.flush()  # asks the database for the new id without finishing
        else:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None:
                raise ConversationNotFound(f"There is no conversation {conversation_id}.")
        conversation.updated_at = utcnow()
        session.add(Message(conversation_id=conversation.id, role=role, content=content, run_id=run_id))
        session.commit()
        return conversation.id
