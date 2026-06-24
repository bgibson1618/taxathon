"""The hand-rolled agent loop (F4 — the "chat loop" pillar).

``run_turn(state, user_msg)`` runs ONE user turn: it appends the user message,
then loops calling OpenRouter — ``while finish_reason == 'tool_calls'`` — and
dispatches each requested tool through :func:`app.agent.tools.dispatch`,
appending the tool results back into the transcript, until the model emits a
natural-language turn (no tool calls). That final assistant message is returned.

No framework, no graph compiler — the loop is meant to be read top-to-bottom by a
judge (ARCHITECTURE Key Decision 1 / DECISION_LOG D3). It owns:

* the ``finish_reason == 'tool_calls'`` dispatch loop;
* a **max-iteration guard** so a misbehaving model can never spin forever;
* **retry-once on a transient LLM error** (one re-issue of the same request).

Streaming (only the final natural-language turn streams) is layered on later by
F8; here every call is a non-streamed request/response, which is exactly what the
tool-deciding calls need.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.agent import tools
from app.agent.state import SessionState
from app.config import PRIMARY_MODEL
from app.llm import LLMError, chat_completion, extract_tool_calls, first_message
from app.observe import record

logger = logging.getLogger(__name__)

#: Hard ceiling on tool-call rounds in a single turn. Generous enough for the
#: real flow (extract_w2 -> ask_user -> set_filing_status -> compute_1040 is 4)
#: but a firm stop so a model that loops on tools can never spin forever (F4:
#: "the loop terminates cleanly (no infinite tool loop)").
MAX_TOOL_ITERATIONS: int = 8

#: The system prompt that frames the agent. Behavior-bearing guardrails live in
#: CODE (F5), not here — this only sets the warm, one-question-at-a-time tone and
#: tells the model which tools exist and the order they are used.
SYSTEM_PROMPT = (
    "You are Taxathon, a warm, friendly assistant that helps a user file a simple "
    "2025 US federal tax return from a single W-2. You are not a tax advisor and "
    "do not give tax advice; you only help complete this one return.\n\n"
    "You have these tools and must use them — never compute a number yourself:\n"
    "  - extract_w2: read the user's uploaded W-2 into structured fields.\n"
    "  - ask_user: ask the user ONE short, plain-language question. This is the "
    "only way to ask the user anything. Keep questions to a strict budget of at "
    "most 5; ask one at a time.\n"
    "  - set_filing_status: record the user's filing status once they tell you.\n"
    "  - compute_1040: compute the return once the W-2 is extracted and the "
    "filing status is set.\n\n"
    "Typical flow: if a W-2 has been uploaded, call extract_w2; ask the user for "
    "their filing status with ask_user; call set_filing_status with their answer; "
    "then call compute_1040 and tell them the result warmly and plainly. Speak "
    "like a helpful person, not a form."
)

GREETING = (
    "Hi! I'm here to help you file a simple 2025 federal return from your W-2. "
    "Go ahead and upload your W-2 whenever you're ready, and I'll take it from there."
)


@dataclass(frozen=True)
class TurnResult:
    """The outcome of one :func:`run_turn`.

    ``content`` is the assistant's natural-language reply (what the user sees).
    ``tool_calls_made`` is the ordered list of tool names dispatched this turn —
    handy for the smoke script's "what tools fired" evidence and for tests.
    """

    content: str
    tool_calls_made: list[str]
    iterations: int


def initial_messages() -> list[dict[str, Any]]:
    """The seed transcript for a new session: system prompt + warm greeting."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "assistant", "content": GREETING},
    ]


# Injection seam for tests: the loop calls THIS, not chat_completion directly, so
# a unit test can swap in a deterministic fake LLM without hitting the network.
LLMFn = Callable[..., dict[str, Any]]


def _call_llm_with_retry(
    llm_fn: LLMFn,
    messages: list[dict[str, Any]],
    *,
    model: str,
) -> dict[str, Any]:
    """Issue one tool-enabled chat call, retrying once on a transient error.

    A single re-issue covers a flaky network / 5xx (F4: "retries a transient LLM
    error once"). A second failure is re-raised for the caller to surface.
    """
    try:
        return llm_fn(
            messages,
            model=model,
            tools=tools.tool_schemas(),
        )
    except LLMError as exc:
        logger.warning("LLM call failed (%s); retrying once", exc)
        # One retry. If this also fails, the exception propagates.
        return llm_fn(
            messages,
            model=model,
            tools=tools.tool_schemas(),
        )


def _emit_progress(progress: Optional[Callable[[dict[str, Any]], None]], event: dict[str, Any]) -> None:
    """Invoke the F8 progress callback, swallowing any error.

    Progress events are pure observability for the streaming UI; a failure here
    (a closed client, a buggy callback) must never break the agent loop.
    """
    if progress is None:
        return
    try:
        progress(event)
    except Exception:  # noqa: BLE001 — observability must not break the loop
        logger.debug("progress callback raised; ignoring", exc_info=True)


def _finish_reason(response: dict[str, Any]) -> Optional[str]:
    choices = response.get("choices") or []
    if not choices:
        return None
    return choices[0].get("finish_reason")


def _summarize_tool_result(name: str, result: dict[str, Any]) -> str:
    """A short, judge-readable summary of a tool result for the trace (F6).

    Kept compact (the full payload is already in the transcript). For ``ask_user``
    it surfaces the *question text* — per F4, questions reach the user via the tool
    result, not NL prose, so the trace must capture the question itself to be a
    faithful turn-by-turn record. Redaction happens at ``record`` write-time.
    """
    if not isinstance(result, dict):
        return str(result)[:200]
    if name == "ask_user" and result.get("question"):
        return f"asked: {result['question']}"
    if not result.get("ok", True):
        # A tool/guardrail failure: surface the error so the judge sees why.
        return f"error: {result.get('error', 'tool reported failure')}"
    # A successful tool: surface the most salient fields without dumping the lot.
    salient = [
        f"{k}={result[k]}"
        for k in ("filing_status", "wages", "refund", "amount_owed", "questions_asked")
        if k in result
    ]
    return ("ok " + ", ".join(salient)).strip() if salient else "ok"


def _trace_args(raw_args: Any) -> dict[str, Any]:
    """Best-effort parse of a tool_call's raw ``arguments`` into a dict for the trace.

    The model sends ``arguments`` as a JSON string (or, in tests, a dict). We parse
    leniently here purely for the trace record — dispatch does its own strict
    validation. A value we cannot parse into a dict is preserved as ``{"raw": ...}``
    so the record still shows *what was attempted*. Redaction is applied later in
    ``record``.
    """
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str) and raw_args.strip():
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            return {"raw": raw_args}
        return parsed if isinstance(parsed, dict) else {"raw": parsed}
    return {}


def _guardrail_verdict(name: str, result: dict[str, Any]) -> tuple[str, str]:
    """Map a tool result to a (decision, verdict) pair for the trace.

    A guardrail *block* (the F5 hook denied the call — ``blocked: True``) is a
    ``refuse`` decision with a ``"refuse"`` verdict; everything else that ran is a
    ``tool`` decision that was ``"allow"``-ed through the gate.
    """
    if isinstance(result, dict) and result.get("blocked"):
        return "refuse", "refuse"
    return "tool", "allow"


#: A progress callback (F8 streaming seam). The loop invokes it with a small
#: event dict at notable points so a streaming caller can emit live progress —
#: principally ``{"type": "tool", "name": <tool>}`` just before each tool runs,
#: so a tool-running turn shows a working indicator instead of dead air. It is
#: ``None`` by default, so the non-streaming ``/chat`` path is unaffected.
ProgressFn = Callable[[dict[str, Any]], None]


def run_turn(
    state: SessionState,
    user_msg: Optional[str],
    *,
    model: str = PRIMARY_MODEL,
    llm_fn: Optional[LLMFn] = None,
    progress: Optional[ProgressFn] = None,
) -> TurnResult:
    """Run one user turn to completion and return the assistant's reply.

    Appends ``user_msg`` (if any) to ``state.messages``, then loops: call the
    model with the tool schemas; if it requested tool calls, dispatch each and
    append the results as ``tool`` messages, then call again; stop when the model
    returns a natural-language message (no tool calls) or the iteration guard
    trips. ``state.messages`` carries the full transcript across turns, which is
    how the agent remembers earlier answers.

    Args:
        state: the live session (mutated in place — messages, w2, computed, ...).
        user_msg: the new user message, or ``None`` to let the model act on the
            existing transcript (e.g. right after a W-2 upload).
        model: the OpenRouter model id (defaults to the pinned primary).
        llm_fn: the chat-completion callable (injection seam for tests). When
            ``None`` (the default) the module-level :func:`chat_completion` is
            resolved at call time, so a monkeypatch of ``loop.chat_completion``
            (e.g. the F8 stream tests) is honoured without threading ``llm_fn``
            through the HTTP route.
        progress: an optional callback (F8 streaming). Called with a small event
            dict before each tool dispatch — ``{"type": "tool", "name": <tool>}``
            — so a streaming caller can render a live working indicator instead of
            dead air during tool turns. ``None`` keeps the non-streaming path
            unchanged. A raised exception from the callback is swallowed so
            observability can never break the loop.

    Returns:
        A :class:`TurnResult` with the assistant's reply and the tools fired.
    """
    # Resolve the LLM callable at call time so a monkeypatch of the module-level
    # `chat_completion` (the F8 stream tests) is picked up; an explicit `llm_fn`
    # (the F4 unit tests) still wins.
    if llm_fn is None:
        llm_fn = chat_completion

    if user_msg is not None:
        state.messages.append({"role": "user", "content": user_msg})

    tool_calls_made: list[str] = []

    for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
        response = _call_llm_with_retry(llm_fn, state.messages, model=model)
        message = first_message(response)
        finish_reason = _finish_reason(response)
        tool_calls = extract_tool_calls(response)

        # A natural-language turn (no tool calls requested) ends the loop.
        if finish_reason != "tool_calls" and not tool_calls:
            content = message.get("content") or ""
            # Record the assistant's final message in the transcript.
            state.messages.append({"role": "assistant", "content": content})
            # F6 — record the natural-language ("talk") turn so the trace captures
            # the agent's spoken decision, not just its tool dispatches.
            record(
                state,
                "talk",
                result_summary=content,
            )
            return TurnResult(
                content=content,
                tool_calls_made=tool_calls_made,
                iterations=iteration,
            )

        # The model wants tools. Append the assistant tool-call message verbatim
        # (the API requires the tool results to reference its tool_call ids).
        state.messages.append(_assistant_tool_call_message(message, tool_calls))

        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name", "")
            raw_args = fn.get("arguments")
            tool_calls_made.append(name)
            trace_args = _trace_args(raw_args)
            # F8 — emit a tool-progress event so a streaming caller can show a
            # live working indicator (no dead air) while this tool runs. Best
            # effort: a callback error must never break the loop.
            _emit_progress(progress, {"type": "tool", "name": name})
            started = time.perf_counter()
            try:
                result = tools.dispatch(state, name, raw_args)
            except tools.ToolError as exc:
                # Malformed call: no tool body ran. Report it back so the model
                # can correct itself, and keep the loop alive.
                result = {"ok": False, "error": f"Invalid tool call: {exc}"}
            latency_ms = (time.perf_counter() - started) * 1000.0

            # F6 — record this tool dispatch (or refusal, if a guardrail blocked
            # it). Args + summary are SSN-redacted at write time inside record().
            decision, verdict = _guardrail_verdict(name, result)
            record(
                state,
                decision,
                tool_name=name,
                args=trace_args,
                result_summary=_summarize_tool_result(name, result),
                guardrail_verdict=verdict,
                latency_ms=latency_ms,
            )

            state.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "name": name,
                    "content": json.dumps(result),
                }
            )

    # Iteration guard tripped — the model kept requesting tools. Stop cleanly with
    # a graceful message rather than spinning forever (F4).
    logger.warning(
        "run_turn hit MAX_TOOL_ITERATIONS=%s without a final message", MAX_TOOL_ITERATIONS
    )
    fallback = (
        "Sorry — I got a little tangled up working through that. Could you try "
        "rephrasing, or let me know how you'd like to continue?"
    )
    state.messages.append({"role": "assistant", "content": fallback})
    # F6 — the guard-trip fallback is still a spoken turn; record it so the trace
    # shows the loop ended gracefully rather than silently.
    record(
        state,
        "talk",
        result_summary=fallback,
        guardrail_verdict="max_iterations",
    )
    return TurnResult(
        content=fallback,
        tool_calls_made=tool_calls_made,
        iterations=MAX_TOOL_ITERATIONS,
    )


def _assistant_tool_call_message(
    message: dict[str, Any], tool_calls: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the assistant message that carries the tool calls for the transcript.

    Preserves the original ``tool_calls`` (with their ids) so the subsequent
    ``tool`` result messages reference them, as the chat-completions API requires.
    """
    return {
        "role": "assistant",
        "content": message.get("content") or "",
        "tool_calls": tool_calls,
    }
