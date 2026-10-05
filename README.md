# AI Dashboard

A minimal chatbot that will grow into a personal life dashboard.

## Structure

```
AIDashboard/
├── app/
│   ├── config.py   settings from .env
│   ├── llm.py      the only file that calls the model API
│   ├── tools.py    functions the model can call (add calendar, Gmail, weather here)
│   ├── agent.py    system prompt + tool-use loop  ← the "brain"
│   └── server.py   FastAPI: serves the page, POST /api/chat
├── static/
│   └── index.html  chat UI (plain HTML + JS, no build step)
└── cli.py          terminal chat, same agent
```

Each layer only knows about the one below it:
`index.html / cli.py → server.py → agent.py → llm.py + tools.py`

## How one message flows

1. The browser sends the full conversation to `POST /api/chat`.
2. `agent.reply()` prepends the system prompt and calls the model with the tool schemas.
3. If the model asks for a tool, the agent runs it, appends the result and calls the model again (up to 5 rounds).
4. The final text goes back to the browser, which adds it to its history.

The server keeps no state. Restarting it loses nothing; refreshing the page clears the chat.

## Run

```bash
cp .env.example .env      # then fill in your key / base URL / model
uv sync
uv run uvicorn app.server:app --reload    # open http://localhost:8000
uv run python cli.py                      # or chat in the terminal
```

The model must support tool calling (most current OpenAI-compatible models do).

## Where to go next

- **New capability:** add a function + schema in `tools.py`. Nothing else changes.
- **Personality / rules:** edit `SYSTEM_PROMPT` in `agent.py`.
- **Streaming replies:** `stream=True` in `llm.py` + a streaming response in `server.py`.
- **Memory across sessions:** save `history` server-side (a JSON file or SQLite) instead of in the browser.
- **Dashboard panels:** add `GET` endpoints in `server.py` that return data directly from tools (no LLM), and render them next to the chat.
