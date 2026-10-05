# AI Dashboard

A personal agent that will grow into a life dashboard: calendar, inbox,
coursework and weather in one place, with actions you approve.

**Status:** Phase 1 (foundation): streaming chat with saved conversations,
a tool registry, a weather tool, and a trace view of every step the agent takes.

## Run it

```bash
cp .env.example .env              # fill in LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_ID
mkdir -p data && cp profile.example.md data/profile.md   # optional: tell the agent about you
uv sync
uv run uvicorn app.main:app --reload    # http://localhost:8000
uv run python cli.py                    # or chat in the terminal
uv run pytest                           # tests (no API key or network needed)
```

Any OpenAI-compatible provider works, but the model must support tool calling.

The server only answers requests addressed to the host names in
`ALLOWED_HOSTS` (default `localhost,127.0.0.1`); anything else gets a 400.
That stops other websites from reaching your chats through your browser.
To open the app from your phone over Tailscale, add your computer's
Tailscale machine name to `ALLOWED_HOSTS` in `.env`.
`http://localhost:8000/traces` shows what the agent did for each message;
`http://localhost:8000/docs` lists every API endpoint.

## Structure

```
app/
├── main.py              creates the web app; serves the two pages
├── config.py            every setting, from .env
├── api/                 HTTP routes only, no logic
│   ├── chat.py          POST /api/chat (streams), conversation list + messages
│   └── traces.py        GET /api/runs, /api/runs/{id}
├── agent/               the brain
│   ├── loop.py          the agent loop: model → tools → model … (start here)
│   ├── llm.py           the only file that calls the model; streaming
│   ├── context.py       builds the briefing: rules + time + profile + history
│   ├── tracing.py       logs every model and tool call
│   └── prompts/system.md   the agent's standing instructions
├── tools/               what the model may call
│   ├── registry.py      @tool decorator, permission tiers, schemas, run()
│   ├── clock.py         get_current_time
│   └── weather.py       get_weather
├── integrations/        plain API clients, no model
│   └── openmeteo.py     Open-Meteo weather + geocoding (free, no key)
└── db/
    ├── models.py        tables: Conversation, Message, Trace
    └── session.py       the SQLite connection (data/app.db)
static/                  index.html (chat), traces.html (trace view)
tests/                   pytest with a scripted fake model
data/                    git-ignored: app.db, profile.md
```

Each layer only calls the one below it:
`pages / cli.py → api/ → agent/ → tools/ → integrations/`, with `db/` underneath.

Suggested reading order: `agent/loop.py` → `agent/llm.py` → `tools/registry.py`
→ `tools/weather.py` → `api/chat.py` → `static/index.html`.

## How one message flows

1. The page POSTs your message and the conversation id to `/api/chat`.
2. `loop.run_turn()` saves it, then builds the briefing from `context.py`:
   system prompt, current time, your profile, the last 40 messages.
3. The model is called with streaming. Text pieces go straight to the page as
   Server-Sent Events; tool requests are assembled from their fragments.
4. If the model asked for tools, `registry.run()` checks the tier and the
   arguments, runs them, and the loop calls the model again with the results
   (at most 5 rounds, and within a token budget).
5. The visible reply is saved. Every model and tool call is in the `trace` table.

## Adding a tool

Write a function in `app/tools/` and decorate it. That's all: the docstring,
type hints and `Field` descriptions become the schema the model sees, and
arguments are validated before your function runs.

```python
@tool(tier=Tier.READ)
def get_forecast(place: Annotated[str, Field(description="City name")]) -> dict:
    """One-line description the model reads."""
    ...
```

If it's a new file, add it to the import in `app/tools/__init__.py`.
Every tool must name its tier. Tools that change things use `Tier.PROPOSE`;
until the approval queue exists (Phase 4) the registry refuses to run them.
`Tier.HANDOFF` tools (money, irreversible) are never run by the app.

## Notes

- Changing a table in `db/models.py`: the app creates missing tables but
  doesn't alter existing ones. While developing, delete `data/app.db`.
  A chat tab that was open at the time will say its conversation no longer
  exists the next time you send, switch to a new chat and keep your message
  in the box. Nothing is saved until you send again. Likewise
  `cli.py <id>` with an id that doesn't exist stops with a message.
- The full design and roadmap are in the AIDashboard design doc.
