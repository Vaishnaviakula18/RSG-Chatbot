"""Orchestration: question -> plan -> validation -> SQL -> structured answer."""
import os

from . import nlu
from .analytics import run_plan
from .db import get_catalog

MAX_LEN = 500


class AppError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def ask(conn, question, llm_fn=None):
    q = (question or "").strip()
    if not q:
        raise AppError(400, "Question must not be empty.")
    if len(q) > MAX_LEN:
        raise AppError(400, f"Question is too long (max {MAX_LEN} characters).")
    catalog = get_catalog(conn)

    llm = llm_fn or (nlu.llm_plan if os.getenv("OPENAI_API_KEY") else None)
    plan, by, notes = None, "rules", []
    if llm:
        try:
            plan, by = llm(q, catalog), "openai"
        except Exception as exc:  # network, auth, bad JSON... -> degrade gracefully
            notes.append(f"OpenAI unavailable ({type(exc).__name__}); used the rule-based interpreter instead.")
    if plan is None:
        plan = nlu.rule_based_plan(q, catalog)

    try:
        clean = nlu.validate_plan(plan, catalog)
    except nlu.PlanError as exc:
        return {"status": "unsupported", "question": q, "message": str(exc), "interpreted_by": by,
                "examples": nlu.EXAMPLES, "notes": notes}
    try:
        result = run_plan(conn, clean)
    except Exception as exc:
        raise AppError(500, "Internal error while running the query.") from exc
    return {"status": "ok", "question": q, "interpreted_by": by, "plan": clean, "notes": notes, **result}
