"""
Shared test setup. pytest loads this file automatically before any test.

Two rules for all tests:
  1. Never touch your real data: DATA_DIR points at a throwaway folder,
     set BEFORE any app module is imported (config reads it at import time).
  2. Never call a real model: `fake_llm` replaces llm.stream with a script.
"""
import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="aidashboard-test-")
os.environ["LLM_API_KEY"] = "test-key"
os.environ["LLM_MODEL_ID"] = "test-model"

import pytest  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.agent import llm  # noqa: E402
from app.db.session import engine, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts with empty tables."""
    SQLModel.metadata.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the model with a script.

    Usage:
        script = fake_llm([
            [ModelReply("", [ToolCall("c1", "get_current_time", "{}")])],     # 1st model call
            [TextDelta("It is "), TextDelta("noon."), ModelReply("It is noon.")],  # 2nd call
        ])
    Each inner list is what one model call yields. `script.calls` records the
    messages each call received, so tests can check what the model saw.
    """
    class Script:
        def __init__(self, replies):
            self.replies = list(replies)
            self.calls = []

        def stream(self, messages, tools=None, model=None):
            # Copy the list: the loop keeps appending to it after this call.
            self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
            if not self.replies:
                raise AssertionError("fake model called more times than scripted")
            yield from self.replies.pop(0)

    def install(replies):
        script = Script(replies)
        monkeypatch.setattr(llm, "stream", script.stream)
        return script

    return install
