"""llm.stream(): turning provider chunks into TextDelta pieces and one ModelReply.

The chunks below mimic the OpenAI streaming format: text and tool calls
arrive in fragments spread over many chunks.
"""
from types import SimpleNamespace as NS

from app.agent import llm


def text_chunk(text):
    return NS(usage=None, choices=[NS(delta=NS(content=text, tool_calls=None))])


def tool_chunk(index=None, id=None, name=None, args=None):
    fragment = NS(index=index, id=id, function=NS(name=name, arguments=args))
    return NS(usage=None, choices=[NS(delta=NS(content=None, tool_calls=[fragment]))])


def usage_chunk(prompt, completion):
    return NS(usage=NS(prompt_tokens=prompt, completion_tokens=completion), choices=[])


def run(monkeypatch, chunks):
    monkeypatch.setattr(llm, "_open_stream", lambda kwargs: iter(chunks))
    return list(llm.stream([{"role": "user", "content": "hi"}]))


def test_text_pieces_then_reply(monkeypatch):
    items = run(monkeypatch, [text_chunk("Hel"), text_chunk("lo"), usage_chunk(10, 2)])
    assert [i.text for i in items[:-1]] == ["Hel", "lo"]
    assert items[-1] == llm.ModelReply("Hello", [], 10, 2)


def test_tool_call_fragments_are_joined(monkeypatch):
    items = run(monkeypatch, [
        tool_chunk(0, "call_1", "get_weather", ""),
        tool_chunk(0, args='{"pla'), tool_chunk(0, args='ce": "Shan'), tool_chunk(0, args='ghai"}'),
        tool_chunk(1, "call_2", "get_current_time", "{}"),
    ])
    reply = items[-1]
    assert [(c.id, c.name, c.arguments) for c in reply.tool_calls] == [
        ("call_1", "get_weather", '{"place": "Shanghai"}'), ("call_2", "get_current_time", "{}")]


def test_provider_without_index(monkeypatch):
    items = run(monkeypatch, [
        tool_chunk(None, "a", "get_weather", '{"place":'), tool_chunk(None, args=' "Paris"}'),
        tool_chunk(None, "b", "get_current_time", "{}"),
    ])
    assert [(c.id, c.arguments) for c in items[-1].tool_calls] == [("a", '{"place": "Paris"}'), ("b", "{}")]
