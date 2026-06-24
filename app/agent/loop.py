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


def _finish_reason(response: dict[str, Any]) -> Optional[str]:
    choices = response.get("choices") or []
    if not choices:
        return None
    return choices[0].get("finish_reason")


def run_turn(
    state: SessionState,
    user_msg: Optional[str],
    *,
    model: str = PRIMARY_MODEL,
    llm_fn: LLMFn = chat_completion,
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
        llm_fn: the chat-completion callable (injection seam for tests).

    Returns:
        A :class:`TurnResult` with the assistant's reply and the tools fired.
    """
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
            try:
                result = tools.dispatch(state, name, raw_args)
            except tools.ToolError as exc:
                # Malformed call: no tool body ran. Report it back so the model
                # can correct itself, and keep the loop alive.
                result = {"ok": False, "error": f"Invalid tool call: {exc}"}
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
