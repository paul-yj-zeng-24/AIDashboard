"""The agent loop: events, tool rounds, memory, traces, safety valves."""
from sqlmodel import select

from app import config
from app.agent import loop
from app.agent.llm import ModelReply, TextDelta, ToolCall
from app.db.models import Message, Trace
from app.db.session import new_session


def events_of(conversation_id, text):
    return list(loop.run_turn(conversation_id, text))


def test_plain_answer_streams_and_is_saved(fake_llm):
    fake_llm([[TextDelta("Hel"), TextDelta("lo!"), ModelReply("Hello!", tokens_in=50, tokens_out=3)]])
    events = events_of(None, "hi")

    kinds = [e["type"] for e in events]
    assert kinds == ["conversation", "text", "text", "done"]
    conversation_id, run_id = events[0]["id"], events[-1]["run_id"]

    with new_session() as s:
        msgs = s.exec(select(Message).order_by(Message.id)).all()
        assert [(m.role, m.content) for m in msgs] == [("user", "hi"), ("assistant", "Hello!")]
        assert all(m.conversation_id == conversation_id and m.run_id == run_id for m in msgs)
        traces = s.exec(select(Trace)).all()
        assert [(t.kind, t.tokens_in, t.tokens_out) for t in traces] == [("model", 50, 3)]


def test_tool_round_then_answer(fake_llm):
    script = fake_llm([
        [ModelReply("", [ToolCall("call_1", "get_current_time", '{"timezone": "Asia/Shanghai"}')])],
        [TextDelta("It's late in Shanghai."), ModelReply("It's late in Shanghai.")],
    ])
    events = events_of(None, "time in Shanghai?")
    kinds = [e["type"] for e in events]
    assert kinds == ["conversation", "tool_start", "tool_end", "text", "done"]
    assert events[2]["ok"] is True

    # The second model call saw the tool request and its result, linked by id.
    second = script.calls[1]["messages"]
    assert second[-2]["tool_calls"][0]["id"] == "call_1"
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "call_1"
    assert "CST" in second[-1]["content"]

    with new_session() as s:
        steps = s.exec(select(Trace).order_by(Trace.id)).all()
        assert [(t.kind, t.name, t.step) for t in steps] == [
            ("model", "test-model", 0), ("tool", "get_current_time", 0), ("model", "test-model", 1)]


def test_history_is_loaded_from_the_database(fake_llm):
    """Done-when for Phase 1: a conversation survives a restart. The second
    turn gets its history from SQLite, not from the caller."""
    script = fake_llm([[TextDelta("First answer"), ModelReply("First answer")],
                       [TextDelta("Second answer"), ModelReply("Second answer")]])
    conversation_id = events_of(None, "first question")[0]["id"]
    events_of(conversation_id, "second question")

    seen = [(m["role"], m["content"]) for m in script.calls[1]["messages"][1:]]  # skip system prompt
    assert seen == [("user", "first question"), ("assistant", "First answer"), ("user", "second question")]


def test_system_prompt_has_time_and_profile(fake_llm):
    config.PROFILE_PATH.write_text("I study CS at Berkeley.")
    try:
        script = fake_llm([[ModelReply("ok")]])
        events_of(None, "hi")
        system = script.calls[0]["messages"][0]
        assert system["role"] == "system"
        assert "Current time:" in system["content"] and "I study CS at Berkeley." in system["content"]
    finally:
        config.PROFILE_PATH.unlink()


def test_last_round_offers_no_tools(fake_llm):
    """A model that keeps asking for tools gets one final call without tools,
    so it has to answer with what it has."""
    rounds = [[ModelReply("", [ToolCall(f"c{i}", "get_current_time", "{}")])] for i in range(config.MAX_STEPS - 1)]
    script = fake_llm(rounds + [[TextDelta("Best I can do."), ModelReply("Best I can do.")]])
    events = events_of(None, "loop forever")
    assert sum(e["type"] == "tool_start" for e in events) == config.MAX_STEPS - 1
    assert script.calls[-1]["tools"] is None and script.calls[0]["tools"]
    assert "".join(e["delta"] for e in events if e["type"] == "text") == "Best I can do."


def test_tool_calls_on_last_round_are_not_run(fake_llm):
    rounds = [[ModelReply("", [ToolCall(f"c{i}", "get_current_time", "{}")])] for i in range(config.MAX_STEPS)]
    fake_llm(rounds)
    events = events_of(None, "loop forever")
    assert sum(e["type"] == "tool_start" for e in events) == config.MAX_STEPS - 1
    assert "too many tool steps" in "".join(e["delta"] for e in events if e["type"] == "text")


def test_disconnect_mid_reply_still_saves_it(fake_llm):
    """Closing the tab stops the generator; what was shown must still be saved."""
    fake_llm([[TextDelta("Half a "), TextDelta("reply"), ModelReply("Half a reply")]])
    turn = loop.run_turn(None, "hi")
    next(turn)                     # conversation event
    assert next(turn)["delta"] == "Half a "
    turn.close()                   # what Python does when the browser goes away
    with new_session() as s:
        assert [(m.role, m.content) for m in s.exec(select(Message).order_by(Message.id))] == [
            ("user", "hi"), ("assistant", "Half a")]
        assert s.exec(select(Trace)).one().error == "cancelled: the client disconnected"


def test_setup_error_is_reported(fake_llm, monkeypatch):
    def broken(conversation_id):
        raise ValueError("bad profile")

    monkeypatch.setattr(loop.context, "build_messages", broken)
    events = events_of(None, "hi")
    assert {"type": "error", "message": "ValueError: bad profile"} in events
    assert events[-1]["type"] == "done"


def test_model_error_is_reported_and_traced(fake_llm, monkeypatch):
    def broken(messages, tools=None, model=None):
        raise RuntimeError("provider is down")
        yield  # makes this a generator, like the real stream()

    monkeypatch.setattr(loop.llm, "stream", broken)
    events = events_of(None, "hi")
    assert events[-2] == {"type": "error", "message": "RuntimeError: provider is down"}
    with new_session() as s:
        trace = s.exec(select(Trace)).one()
        assert trace.error == "RuntimeError: provider is down"
        # The user's message is kept; no empty assistant message is saved.
        assert [m.role for m in s.exec(select(Message)).all()] == ["user"]


def test_text_before_and_after_tools_is_separated(fake_llm):
    fake_llm([
        [TextDelta("Let me check."), ModelReply("Let me check.", [ToolCall("c1", "get_current_time", "{}")])],
        [TextDelta("Done."), ModelReply("Done.")],
    ])
    events_of(None, "time?")
    with new_session() as s:
        reply = s.exec(select(Message).where(Message.role == "assistant")).one()
        assert reply.content == "Let me check.\n\nDone."
