"""Live observation trace (F6 — the "observability" pillar).

Every decision the agent makes — each tool dispatch, each natural-language turn,
each refusal/guardrail block — is recorded as a structured :class:`TraceRecord`
and appended to ``state.trace``. ``GET /trace/{session_id}`` (in ``app.main``)
serves the redacted trail live, and the F8 UI panel polls it, so a judge can
watch the agent's decisions turn-by-turn while it runs (ARCHITECTURE: "Observation
is a code obligation in the loop"; FEATURES F6).

Recording is a **code obligation**, not a prompt instruction: :func:`record` is
called at every decision point in :mod:`app.agent.loop` (and through the dispatch
seam in :mod:`app.agent.tools`). The LLM cannot suppress or fabricate a record.

Redaction
---------
SSN-shaped values are redacted **at write time** so a raw SSN can never reach the
trail (FEATURES F6: "SSN-shaped values are redacted in every trace record"). The
canonical redactor is :func:`app.guardrails.redact_ssn` (F5); if that module is
not yet importable (parallel build wave), we fall back to a local regex with the
same behavior. Redaction is applied recursively to the tool ``args`` and to the
``result_summary`` string before they land in the record.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# SSN redaction — prefer the canonical F5 redactor; fall back to a local regex.
# ---------------------------------------------------------------------------
# Matches an SSN written with or without separators: 123-45-6789 / 123 45 6789 /
# 123456789. Word boundaries keep it from chewing into longer digit runs (e.g. a
# 12-digit account number). Mirrors the masking used by the W-2 model.
_SSN_RE = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
_SSN_REDACTED = "***-**-****"


def _local_redact_ssn(text: str) -> str:
    """Replace any SSN-shaped substring with a redaction marker (local fallback)."""
    return _SSN_RE.sub(_SSN_REDACTED, text)


def _resolve_redactor() -> Callable[[str], str]:
    """Return ``app.guardrails.redact_ssn`` if importable, else the local fallback.

    Resolved lazily (per call) rather than at import time so the trace does not
    hard-depend on F5's module existing when F6 is built/imported in a parallel
    wave. Once F5 lands, its redactor is picked up automatically.
    """
    try:
        from app.guardrails import redact_ssn  # type: ignore

        return redact_ssn
    except Exception:  # noqa: BLE001 — any import failure -> local fallback
        return _local_redact_ssn


def _redact(value: Any, redactor: Callable[[str], str]) -> Any:
    """Recursively redact SSN-shaped values in strings, dicts, and lists."""
    if isinstance(value, str):
        return redactor(value)
    if isinstance(value, dict):
        return {k: _redact(v, redactor) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v, redactor) for v in value]
    return value


# ---------------------------------------------------------------------------
# The record.
# ---------------------------------------------------------------------------
@dataclass
class TraceRecord:
    """One structured decision point in the agent's run.

    Fields (FEATURES F6: "turn, decision, tool, redacted args, result, guardrail
    verdict"):

    * ``turn`` — monotonically increasing index within the session's trace.
    * ``decision`` — one of ``"tool"`` / ``"talk"`` / ``"refuse"``.
    * ``tool`` — the tool name for a ``tool``/``refuse`` decision, else ``None``.
    * ``args`` — the (redacted) tool arguments dict, or ``{}``.
    * ``result`` — a short, (redacted) human-readable summary of the outcome.
    * ``guardrail_verdict`` — the guardrail decision string (e.g. ``"allow"`` /
      ``"refuse"`` / ``"blocked: budget"``), or ``None`` when not gated.
    * ``latency_ms`` — wall-clock cost of the step, when measured.
    * ``ts`` — epoch seconds the record was written (for live ordering).
    """

    turn: int
    decision: str
    tool: Optional[str] = None
    args: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    guardrail_verdict: Optional[str] = None
    latency_ms: Optional[float] = None
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """The JSON-serializable form stored in ``state.trace`` / served at /trace."""
        return asdict(self)


def record(
    state: Any,
    decision: str,
    tool_name: Optional[str] = None,
    args: Optional[dict[str, Any]] = None,
    result_summary: str = "",
    guardrail_verdict: Optional[str] = None,
    latency_ms: Optional[float] = None,
) -> dict[str, Any]:
    """Append a redacted :class:`TraceRecord` to ``state.trace`` and return it.

    Called at every decision point in the loop (tool dispatch, talk turn,
    refusal). The ``args`` and ``result_summary`` are SSN-redacted **before** they
    are stored, so a raw SSN can never land in the trail (F6). The ``turn`` index
    is derived from the current length of ``state.trace`` so records are ordered
    as they happen.

    Args:
        state: the live :class:`~app.agent.state.SessionState` (its ``.trace`` list
            is appended to). Any object with a ``trace`` list works (keeps F6
            decoupled from the state module's concrete type).
        decision: ``"tool"`` | ``"talk"`` | ``"refuse"``.
        tool_name: the dispatched tool's name (for tool/refuse decisions).
        args: the tool arguments (redacted before storage).
        result_summary: a short outcome string (redacted before storage).
        guardrail_verdict: the guardrail decision, if the step was gated.
        latency_ms: measured wall-clock cost of the step.

    Returns:
        The redacted record dict that was appended (handy for tests / callers).
    """
    redactor = _resolve_redactor()
    trace: list[dict[str, Any]] = getattr(state, "trace", None)
    if trace is None:  # defensive: never crash the loop over observability
        trace = []
        try:
            state.trace = trace  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    rec = TraceRecord(
        turn=len(trace),
        decision=decision,
        tool=tool_name,
        args=_redact(dict(args) if args else {}, redactor),
        result=_redact(result_summary or "", redactor),
        guardrail_verdict=guardrail_verdict,
        latency_ms=latency_ms,
    )
    entry = rec.to_dict()
    trace.append(entry)
    return entry


def get_trace(state: Any) -> list[dict[str, Any]]:
    """Return the session's recorded (already-redacted) trace records.

    A thin accessor so the ``GET /trace`` route does not reach into ``state``
    internals directly. The records are redacted at write time, so this is the
    live, judge-safe view as-is.
    """
    return list(getattr(state, "trace", []) or [])
