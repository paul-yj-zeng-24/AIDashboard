"""
llm.py — the ONLY file that talks to the model provider.

Key idea: an LLM API is stateless. It does not remember earlier calls. Every
request must contain the entire conversation so far as a list of messages:

    [
      {"role": "system",    "content": "You are a helpful assistant..."},
      {"role": "user",      "content": "What time is it?"},
      {"role": "assistant", "content": "..."},
      ...
    ]

The model reads that list and returns ONE new assistant message. That's it.
Everything that feels like "memory" or "agency" is built on top of this
single function by the code in agent.py.

Keeping all provider-specific code here means you can switch providers by
editing .env, or switch SDKs by rewriting only this file.
"""
from functools import lru_cache

from openai import OpenAI

from app import config


# @lru_cache makes this function run only once; later calls return the same
# client object. So the client is created lazily (on first use, not at import
# time) and then reused. Lazy creation means the server can still start and
# show a clear error message if .env is missing.
@lru_cache
def _client() -> OpenAI:
    if not (config.LLM_API_KEY and config.LLM_MODEL_ID):
        raise RuntimeError("Set LLM_API_KEY, LLM_BASE_URL and LLM_MODEL_ID in .env")
    # The "openai" package works with any provider that copies OpenAI's API
    # format; base_url points it at that provider instead of OpenAI.
    return OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)


def complete(messages: list[dict], tools: list[dict] | None = None):
    """Send the conversation to the model once and return its reply.

    messages: the full conversation (see the top of this file).
    tools:    optional descriptions of functions the model is ALLOWED to ask
              for (see tools.py). The model can't run them itself; it can only
              reply "please call get_current_time with these arguments".

    Returns the assistant message object, which has:
      .content     the text reply (may be None if it's asking for tools)
      .tool_calls  None, or a list of tool requests the model wants us to run
    """
    kwargs = {"model": config.LLM_MODEL_ID, "messages": messages}
    if tools:
        kwargs["tools"] = tools

    # One HTTP request to the provider. This is the slow part (~1-10 s).
    response = _client().chat.completions.create(**kwargs)

    # The API can return several alternative answers ("choices"); we only
    # ever ask for one, so take the first.
    return response.choices[0].message
