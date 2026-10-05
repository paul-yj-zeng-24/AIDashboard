"""
tracing.py: writes one row to the `trace` table for every model call and
every tool call. The trace view (/traces) reads these rows back.

Why bother: an agent turn is several hidden steps. When an answer is wrong,
the trace shows where: did the model pick the wrong tool, pass bad arguments,
get a bad result, or misread a good one?
"""
import json
import time

from app.db.models import Trace
from app.db.session import new_session


def to_json(value) -> str:
    """Store anything as readable JSON text (falls back to str() for odd types)."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str, indent=1)


def record(**fields) -> None:
    """Save one trace row. Takes the Trace columns as keyword arguments.
    Opens its own short Session, so a failed agent step can't lose the log."""
    for key in ("input", "output"):
        fields[key] = to_json(fields.get(key, ""))
    with new_session() as session:
        session.add(Trace(**fields))
        session.commit()


class Timer:
    """Measures milliseconds: `t = Timer()` ... `t.ms()`."""
    def __init__(self):
        self.start = time.perf_counter()

    def ms(self) -> int:
        return int((time.perf_counter() - self.start) * 1000)
