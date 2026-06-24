"""F4 unit tests — agent loop + tool dispatch + state, with a MOCKED LLM.

These never touch the network (the live multi-turn proof is the ``observed`` leg
in ``scripts/smoke_agent.py``). They assert the three things the F4 success
criteria call out:

  * malformed tool arguments are rejected before any tool code runs;
  * state is carried across turns (the W-2 and filing status set earlier persist);
  * the loop terminates cleanly (no infinite tool loop) and retries a transient
    LLM error once.

Run: ``uv run pytest tests/test_agent.py``
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.agent import loop, state, tools
from app.agent.state import SessionState, create_session, get_session
from app.llm import LLMError
from app.tax.constants_2025 import FilingStatus

FIXTURE_W2 = Path(__file__).resolve().parent.parent / "fixtures" / "fake_w2.pdf"


# ---------------------------------------------------------------------------
# A tiny scripted fake LLM. Each "step" is the assistant message a real
# chat-completions response would carry. The fake replays them in order and
# shapes them into the OpenRouter response envelope the loop reads.
# ---------------------------------------------------------------------------
def _tool_call(call_id: str, name: str, args: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _response_with_tool_calls(calls: list[dict]) -> dict:
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": "", "tool_calls": calls},
            }
        ]
    }


def _response_with_text(text: str) -> dict:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": text},
            }
        ]
    }


class ScriptedLLM:
    """A fake ``chat_completion`` that replays a fixed list of responses."""

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.calls = 0
        self.seen_messages: list[list[dict]] = []

    def __call__(self, messages, **kwargs):  # signature-compatible with chat_completion
        self.seen_messages.append([dict(m) for m in messages])
        self.calls += 1
        if not self._responses:
            raise AssertionError("ScriptedLLM ran out of responses")
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _clean_sessions():
    """Each test starts with an empty SESSIONS registry and the default guardrail."""
    state.SESSIONS.clear()
    tools.set_guardrail_hook(tools._default_guardrail_hook)
    yield
    state.SESSIONS.clear()
    tools.set_guardrail_hook(tools._default_guardrail_hook)


# ---------------------------------------------------------------------------
# Tool dispatch: malformed args rejected BEFORE the tool body runs.
# ---------------------------------------------------------------------------
def test_dispatch_unknown_tool_raises():
    st = SessionState(session_id="s1")
    with pytest.raises(tools.ToolError):
        tools.dispatch(st, "no_such_tool", "{}")


def test_dispatch_missing_required_arg_rejected():
    st = SessionState(session_id="s1")
    with pytest.raises(tools.ToolError) as exc:
        tools.dispatch(st, "set_filing_status", "{}")
    assert "filing_status" in str(exc.value)
    # The tool never ran, so no status was set.
    assert st.filing_status is None


def test_dispatch_unexpected_arg_rejected():
    st = SessionState(session_id="s1")
    with pytest.raises(tools.ToolError):
        tools.dispatch(st, "ask_user", json.dumps({"question": "hi", "extra": 1}))


def test_dispatch_enum_validation_rejects_bad_status():
    st = SessionState(session_id="s1")
    with pytest.raises(tools.ToolError) as exc:
        tools.dispatch(st, "set_filing_status", json.dumps({"filing_status": "martian"}))
    assert "not one of" in str(exc.value)
    assert st.filing_status is None


def test_dispatch_wrong_type_rejected():
    st = SessionState(session_id="s1")
    with pytest.raises(tools.ToolError):
        # question must be a string, not a number.
        tools.dispatch(st, "ask_user", json.dumps({"question": 42}))


def test_dispatch_unparseable_json_rejected():
    st = SessionState(session_id="s1")
    with pytest.raises(tools.ToolError):
        tools.dispatch(st, "ask_user", "{not json")


# ---------------------------------------------------------------------------
# Tool bodies do real work against state.
# ---------------------------------------------------------------------------
def test_set_filing_status_sets_state():
    st = SessionState(session_id="s1")
    result = tools.dispatch(
        st, "set_filing_status", json.dumps({"filing_status": "head_of_household"})
    )
    assert result["ok"] is True
    assert st.filing_status is FilingStatus.HEAD_OF_HOUSEHOLD


def test_extract_w2_reads_fixture_and_masks_ssn():
    st = SessionState(session_id="s1", upload_path=str(FIXTURE_W2))
    result = tools.dispatch(st, "extract_w2", "{}")
    assert result["ok"] is True
    assert st.w2 is not None
    assert result["wages"] > 0
    # Privacy contract: only the masked SSN leaves the tool.
    assert result["masked_ssn"].startswith("***-**-")
    assert "raw_ssn" not in result
    blob = json.dumps(result)
    assert "ssn" not in blob.lower() or "masked_ssn" in blob


def test_extract_w2_without_upload_returns_error_payload():
    st = SessionState(session_id="s1")  # no upload_path
    result = tools.dispatch(st, "extract_w2", "{}")
    assert result["ok"] is False
    assert "upload" in result["error"].lower()


def test_compute_1040_uses_state_not_model_numbers():
    st = SessionState(session_id="s1", upload_path=str(FIXTURE_W2))
    tools.dispatch(st, "extract_w2", "{}")
    tools.dispatch(st, "set_filing_status", json.dumps({"filing_status": "single"}))
    result = tools.dispatch(st, "compute_1040", "{}")
    assert result["ok"] is True
    assert st.computed is not None
    assert st.computed.filing_status is FilingStatus.SINGLE
    # The result mirrors state.computed exactly (no model-authored numbers).
    assert result["refund"] == str(st.computed.refund)
    assert result["amount_owed"] == str(st.computed.amount_owed)


def test_compute_1040_blocked_until_prerequisites_present():
    st = SessionState(session_id="s1")
    assert tools.dispatch(st, "compute_1040", "{}")["ok"] is False  # no W-2
    st.upload_path = str(FIXTURE_W2)
    tools.dispatch(st, "extract_w2", "{}")
    assert tools.dispatch(st, "compute_1040", "{}")["ok"] is False  # no status


def test_ask_user_increments_question_counter():
    st = SessionState(session_id="s1")
    tools.dispatch(st, "ask_user", json.dumps({"question": "What's your filing status?"}))
    tools.dispatch(st, "ask_user", json.dumps({"question": "Anything else?"}))
    assert st.questions_asked == 2


# ---------------------------------------------------------------------------
# Guardrail seam (the F5 hook) blocks the tool body when it denies.
# ---------------------------------------------------------------------------
def test_guardrail_hook_can_block_tool_body():
    blocked_calls: list[str] = []

    def deny_ask_user(state_, name, args):
        if name == "ask_user":
            blocked_calls.append(name)
            return tools.GuardrailDecision(allow=False, message="Question budget spent.")
        return tools.GuardrailDecision(allow=True)

    tools.set_guardrail_hook(deny_ask_user)
    st = SessionState(session_id="s1")
    result = tools.dispatch(st, "ask_user", json.dumps({"question": "one more?"}))
    assert result["ok"] is False
    assert result["blocked"] is True
    assert "budget" in result["error"].lower()
    # The tool body did NOT run — counter untouched.
    assert st.questions_asked == 0
    assert blocked_calls == ["ask_user"]


# ---------------------------------------------------------------------------
# The loop: state carry, tool dispatch, clean termination.
# ---------------------------------------------------------------------------
def test_loop_terminates_on_plain_text_turn():
    fake = ScriptedLLM([_response_with_text("Hello there!")])
    st = create_session(messages=loop.initial_messages())
    result = loop.run_turn(st, "hi", llm_fn=fake)
    assert result.content == "Hello there!"
    assert result.tool_calls_made == []
    assert fake.calls == 1
    # The user message and the assistant reply are now in the transcript.
    assert st.messages[-1] == {"role": "assistant", "content": "Hello there!"}
    assert any(m.get("role") == "user" and m.get("content") == "hi" for m in st.messages)


def test_loop_dispatches_real_tools_and_carries_state():
    """A scripted multi-step turn: extract_w2 -> set_filing_status -> compute_1040 -> reply.

    Proves the loop dispatches REAL tools (each does real work) and that the
    resulting state (W-2, status, computed return) is carried — not re-derived.
    """
    responses = [
        _response_with_tool_calls([_tool_call("c1", "extract_w2", {})]),
        _response_with_tool_calls(
            [_tool_call("c2", "set_filing_status", {"filing_status": "single"})]
        ),
        _response_with_tool_calls([_tool_call("c3", "compute_1040", {})]),
        _response_with_text("All done — here's your result!"),
    ]
    fake = ScriptedLLM(responses)
    st = create_session(messages=loop.initial_messages())
    st.upload_path = str(FIXTURE_W2)

    result = loop.run_turn(st, "Here's my W-2, I'm single.", llm_fn=fake)

    assert result.content == "All done — here's your result!"
    assert result.tool_calls_made == ["extract_w2", "set_filing_status", "compute_1040"]
    # State carried across the within-turn tool rounds.
    assert st.w2 is not None
    assert st.filing_status is FilingStatus.SINGLE
    assert st.computed is not None
    assert st.computed.refund >= Decimal("0")
    # Tool result messages reference the assistant tool_call ids (API contract).
    tool_msgs = [m for m in st.messages if m.get("role") == "tool"]
    assert {m["tool_call_id"] for m in tool_msgs} == {"c1", "c2", "c3"}


def test_state_carries_across_separate_turns():
    """State set in turn 1 (filing status) is still present in turn 2."""
    st = create_session(messages=loop.initial_messages())

    turn1 = ScriptedLLM(
        [
            _response_with_tool_calls(
                [_tool_call("c1", "set_filing_status", {"filing_status": "head_of_household"})]
            ),
            _response_with_text("Got it — head of household."),
        ]
    )
    loop.run_turn(st, "I'm head of household.", llm_fn=turn1)
    assert st.filing_status is FilingStatus.HEAD_OF_HOUSEHOLD
    n_messages_after_turn1 = len(st.messages)

    # Turn 2 — a plain reply. The earlier status must still be set, and the
    # transcript must have grown (history carried, not reset).
    turn2 = ScriptedLLM([_response_with_text("Anything else?")])
    loop.run_turn(st, "thanks", llm_fn=turn2)
    assert st.filing_status is FilingStatus.HEAD_OF_HOUSEHOLD
    assert len(st.messages) > n_messages_after_turn1


def test_loop_recovers_from_malformed_tool_call():
    """A malformed tool call is reported back, and the loop keeps going."""
    responses = [
        # Model emits a bad set_filing_status (invalid enum) ...
        _response_with_tool_calls(
            [_tool_call("c1", "set_filing_status", {"filing_status": "martian"})]
        ),
        # ... then recovers with a valid one ...
        _response_with_tool_calls(
            [_tool_call("c2", "set_filing_status", {"filing_status": "single"})]
        ),
        _response_with_text("Thanks!"),
    ]
    fake = ScriptedLLM(responses)
    st = create_session(messages=loop.initial_messages())
    result = loop.run_turn(st, "single", llm_fn=fake)

    assert result.content == "Thanks!"
    assert st.filing_status is FilingStatus.SINGLE
    # The malformed call's tool result reports the rejection.
    bad_tool_msg = next(m for m in st.messages if m.get("tool_call_id") == "c1")
    payload = json.loads(bad_tool_msg["content"])
    assert payload["ok"] is False
    assert "Invalid tool call" in payload["error"]


def test_loop_max_iteration_guard_terminates():
    """A model that requests tools forever is stopped by the iteration guard."""
    # Always request a (non-terminating) tool — never a final text turn. (ask_user
    # would end the turn by design, so use extract_w2, which loops without ending.)
    infinite = ScriptedLLM(
        [
            _response_with_tool_calls([_tool_call(f"c{i}", "extract_w2", {})])
            for i in range(loop.MAX_TOOL_ITERATIONS + 5)
        ]
    )
    st = create_session(messages=loop.initial_messages())
    result = loop.run_turn(st, "loop forever", llm_fn=infinite)
    # It terminated (did not hang) and made exactly MAX_TOOL_ITERATIONS calls.
    assert result.iterations == loop.MAX_TOOL_ITERATIONS
    assert infinite.calls == loop.MAX_TOOL_ITERATIONS
    assert result.content  # a graceful fallback message, not empty


def test_loop_retries_transient_llm_error_once():
    """One transient LLMError is retried; the retry's response is used."""

    class FlakyLLM:
        def __init__(self):
            self.calls = 0

        def __call__(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise LLMError("transient 503")
            return _response_with_text("Recovered after retry.")

    flaky = FlakyLLM()
    st = create_session(messages=loop.initial_messages())
    result = loop.run_turn(st, "hi", llm_fn=flaky)
    assert result.content == "Recovered after retry."
    assert flaky.calls == 2  # original + one retry


def test_loop_reraises_after_second_failure():
    """Two consecutive transient errors propagate (retry is once, not forever)."""

    class AlwaysFails:
        def __init__(self):
            self.calls = 0

        def __call__(self, messages, **kwargs):
            self.calls += 1
            raise LLMError("still down")

    always = AlwaysFails()
    st = create_session(messages=loop.initial_messages())
    with pytest.raises(LLMError):
        loop.run_turn(st, "hi", llm_fn=always)
    assert always.calls == 2  # original + exactly one retry, then give up


# ---------------------------------------------------------------------------
# Session state + TTL eviction.
# ---------------------------------------------------------------------------
def test_create_and_get_session_roundtrip():
    st = create_session(messages=loop.initial_messages())
    assert get_session(st.session_id) is st
    assert get_session("nope") is None


def test_expired_session_is_evicted():
    st = create_session()
    # Backdate last_seen beyond the TTL so the next sweep drops it.
    st.last_seen -= state.SESSION_TTL_SECONDS + 1
    assert st.is_expired()
    assert get_session(st.session_id) is None
    assert st.session_id not in state.SESSIONS


def test_active_session_survives_sweep():
    old = create_session()
    old.last_seen -= state.SESSION_TTL_SECONDS + 1
    fresh = create_session()  # this create() triggers a sweep that drops `old`
    assert old.session_id not in state.SESSIONS
    assert get_session(fresh.session_id) is fresh
