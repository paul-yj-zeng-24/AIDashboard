"""
agent.py — the "brain": a system prompt plus the agent loop.

An "agent" is just this loop:

    while True:
        ask the model what to do next
        if it gives a final text answer   -> return it
        if it asks to use tools           -> run them, show it the results, repeat

The model decides WHAT to do; this code decides WHETHER and HOW it happens.
One user message can take several model calls. For example
"What time is it in Shanghai?" goes:

    call 1: model -> "please run get_current_time(timezone='Asia/Shanghai')"
            we run it -> "Saturday 2026-10-03 08:30 CST"
    call 2: model (now seeing that result) -> "It's 8:30 am Saturday in Shanghai."

Same idea as the ReAct demo in datawhale-hello_agents, but there the model
wrote "Action: ..." as text and code had to parse it. Here the API returns
tool requests as structured data (msg.tool_calls), so there is no parsing.
"""
from app import llm, tools

# The system prompt is the agent's standing instructions: who it is, how to
# behave. The model sees it at the top of every request. Changing this text
# is the cheapest way to change the agent's behaviour.
SYSTEM_PROMPT = """You are Paul's personal assistant inside his AI Dashboard.
Be concise and direct. Use a tool whenever it can give you a fact you would
otherwise guess."""

# Safety valve: if the model keeps asking for tools without ever answering
# (a bug, or a confused model), stop after this many rounds instead of
# looping forever and spending money.
MAX_STEPS = 5


def reply(history: list[dict]) -> str:
    """Produce the assistant's next reply.

    history: the visible conversation so far, oldest first, e.g.
        [{"role": "user", "content": "hi"},
         {"role": "assistant", "content": "Hello!"},
         {"role": "user", "content": "what time is it?"}]

    Returns the final reply text.
    """
    # Build the working message list for this turn: the system prompt first,
    # then the conversation. ("*history" unpacks the list into this one.)
    # Tool requests/results get appended to `messages` below. They are
    # scratch work for this turn only and are NOT returned to the caller, so
    # the saved history stays as plain user/assistant text.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]

    for _ in range(MAX_STEPS):
        # Ask the model, telling it which tools exist.
        msg = llm.complete(messages, tools=tools.schemas())

        # Case 1: no tool requests means this is the final answer. Done.
        if not msg.tool_calls:
            return msg.content or ""

        # Case 2: the model wants tools run.
        # First, record its request in the conversation. The API requires
        # this: every "tool" result message must follow the assistant
        # message that asked for it, matched by the call's id.
        messages.append({
            "role": "assistant",
            "content": msg.content,  # often None; sometimes a short "let me check"
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in msg.tool_calls
            ],
        })

        # Then run each requested tool and append its result. The model may
        # ask for several tools at once (e.g. time AND weather).
        for call in msg.tool_calls:
            result = tools.run(call.function.name, call.function.arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,  # links this result to its request
                "content": result,
            })

        # Loop back: the model now sees the results and either answers or
        # asks for more tools.

    return "(Stopped: too many tool steps.)"
