"""F4 — hand-rolled agent loop + tool dispatch + session state.

The "chat loop" and "tools" pillars of the Deterministic Spine, Agentic Skin
(ARCHITECTURE / DECISION_LOG D1, D3). The LLM picks tools and phrases the
conversation; every number-bearing step runs as deterministic Python.

Public surface:
- :mod:`app.agent.state` — typed ``SessionState`` + the in-memory ``SESSIONS``
  dict with TTL eviction (the entire persistence layer).
- :mod:`app.agent.tools` — the typed tool registry + ``dispatch`` (validate-args
  -> guardrail hook (F5 seam) -> run). Tools: ``extract_w2``,
  ``set_filing_status``, ``compute_1040``, ``ask_user``.
- :mod:`app.agent.loop` — ``run_turn`` (the ``while finish_reason=='tool_calls'``
  loop with retry-once and a max-iteration guard).
"""

from app.agent.loop import GREETING, TurnResult, initial_messages, run_turn
from app.agent.state import (
    SESSIONS,
    SessionState,
    create_session,
    get_session,
)

__all__ = [
    "SESSIONS",
    "SessionState",
    "create_session",
    "get_session",
    "GREETING",
    "TurnResult",
    "initial_messages",
    "run_turn",
]
