"""
traces.py: read-only endpoints for the trace view (/traces).

  GET /api/runs            recent turns, one summary row each
  GET /api/runs/{run_id}   every step of one turn, in order
"""
from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from app.db.models import Message, Trace
from app.db.session import new_session

router = APIRouter(prefix="/api")


@router.get("/runs")
def list_runs(limit: int = 50):
    with new_session() as session:
        # One row per run_id, newest first. func.* are SQL aggregate functions:
        # this is "GROUP BY run_id" with counts and sums for each group.
        rows = session.exec(
            select(
                Trace.run_id,
                func.min(Trace.conversation_id),
                func.min(Trace.created_at),
                func.count(Trace.id),
                func.sum(Trace.latency_ms),
                func.sum(Trace.tokens_in),
                func.sum(Trace.tokens_out),
                func.count(Trace.error),  # COUNT ignores NULLs, so this counts errors
            )
            .group_by(Trace.run_id)
            .order_by(func.min(Trace.created_at).desc())
            .limit(limit)
        ).all()

        runs = []
        for run_id, conv_id, started, steps, ms, tin, tout, errors in rows:
            tools = session.exec(
                select(Trace.name).where(Trace.run_id == run_id, Trace.kind == "tool").order_by(Trace.id)
            ).all()
            # The user message that started this turn carries the same run_id.
            question = session.exec(
                select(Message.content).where(Message.run_id == run_id, Message.role == "user")
            ).first()
            runs.append({
                "run_id": run_id, "conversation_id": conv_id, "started_at": started,
                "steps": steps, "latency_ms": ms or 0, "tokens_in": tin, "tokens_out": tout,
                "errors": errors, "tools": tools, "question": question or "",
            })
        return runs


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    with new_session() as session:
        rows = session.exec(select(Trace).where(Trace.run_id == run_id).order_by(Trace.id)).all()
        if not rows:
            raise HTTPException(404, "No such run")
        return rows
