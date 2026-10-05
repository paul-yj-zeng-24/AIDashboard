"""
llm.py: the ONLY file that talks to the model provider.

Key idea (unchanged from Phase 0): an LLM API is stateless. Every request
carries the whole conversation as a list of messages, and the model returns
ONE new assistant message.

New in Phase 1: STREAMING. Instead of waiting 5 seconds for the full reply,
we ask the provider to send it in small pieces ("chunks") as it is written,
and pass each piece on to the browser. Same total time, but you see words
appear immediately.

Streaming makes tool calls slightly harder: a tool request also arrives in
pieces. The name comes once, then the JSON arguments trickle in as fragments
like '{"pla' + 'ce": "Shan' + 'ghai"}'. stream() glues them back together.

stream() is a generator: a function that `yield`s values one at a time.
The caller loops over it:

    for item in llm.stream(messages, tools):
        if isinstance(item, TextDelta): ...   # a piece of text, show it now
        else: ...                             # the final ModelReply, last item
"""
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterator

import openai
from openai import OpenAI

from app import config


@dataclass
class TextDelta:
    """A small piece of the reply text, yielded as soon as it arrives."""
    text: str


@dataclass
class ToolCall:
    id: str         # the provider's id for this request; the result must quote it
    name: str       # which tool
    arguments: str  # JSON text, e.g. '{"place": "Shanghai"}'


@dataclass
class ModelReply:
    """The complete reply, yielded once at the very end of the stream."""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int | None = None   # tokens we sent (prompt), if reported
    tokens_out: int | None = None  # tokens the model wrote, if reported


# Created on first use and then reused (@lru_cache = "remember the result").
@lru_cache
def _client() -> OpenAI:
    if not (config.LLM_API_KEY and config.LLM_MODEL_ID):
        raise RuntimeError("Set LLM_API_KEY, LLM_BASE_URL and LLM_MODEL_ID in .env")
    return OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)


# Asking for token counts while streaming needs an extra option that a few
# OpenAI-compatible providers reject. If one does, we retry without it and
# remember not to ask again.
_provider_reports_usage = True


def _open_stream(kwargs: dict):
    global _provider_reports_usage
    if _provider_reports_usage:
        try:
            return _client().chat.completions.create(**kwargs, stream_options={"include_usage": True})
        except openai.BadRequestError as e:
            # Only give up on token counts if the complaint is about this
            # option. Any other bad request (e.g. conversation too long) is a
            # real error and should surface.
            if "stream_options" not in str(e) and "include_usage" not in str(e):
                raise
            _provider_reports_usage = False
    return _client().chat.completions.create(**kwargs)


def stream(messages: list[dict], tools: list[dict] | None = None,
           model: str | None = None) -> Iterator[TextDelta | ModelReply]:
    """Call the model once, streaming. Yields TextDelta pieces, then one ModelReply."""
    kwargs = {"model": model or config.LLM_MODEL_ID, "messages": messages, "stream": True}
    if tools:
        kwargs["tools"] = tools

    text_parts: list[str] = []
    calls: dict[int, dict] = {}  # tool calls being assembled, keyed by their position
    usage = None

    for chunk in _open_stream(kwargs):
        # The very last chunk may carry only token usage and no choices.
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta  # "what's new since the last chunk"

        if delta.content:
            text_parts.append(delta.content)
            yield TextDelta(delta.content)

        # Tool-call fragments. `index` says which call a fragment belongs to,
        # because the model may request several tools in one reply.
        for fragment in delta.tool_calls or []:
            key = fragment.index
            if key is None:
                # A few providers leave out `index`. Then a fragment with an
                # id we haven't seen starts a new call; anything else
                # continues the most recent one.
                if not calls or (fragment.id and all(c["id"] != fragment.id for c in calls.values())):
                    key = len(calls)
                else:
                    key = max(calls)
            call = calls.setdefault(key, {"id": "", "name": "", "arguments": ""})
            if fragment.id:
                call["id"] = fragment.id
            if fragment.function and fragment.function.name and not call["name"]:
                call["name"] = fragment.function.name
            if fragment.function and fragment.function.arguments:
                call["arguments"] += fragment.function.arguments

    yield ModelReply(
        content="".join(text_parts),
        tool_calls=[ToolCall(**calls[i]) for i in sorted(calls)],
        tokens_in=getattr(usage, "prompt_tokens", None),
        tokens_out=getattr(usage, "completion_tokens", None),
    )
