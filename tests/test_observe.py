"""F6 unit tests — live observation trace (records, redaction, /trace route).

These assert the three F6 success criteria with a MOCKED LLM (no network):

  * every decision point (tool / talk / refuse) writes a structured record
    (turn, decision, tool, redacted args, result, guardrail verdict);
  * SSN-shaped values are redacted in every trace record (at write time);
  * GET /trace returns the live redacted trail, and 404s for an unknown session.

The ``observed`` smoke (a real loop turn -> GET /trace shows turn-by-turn records)
also lives here as ``test_observed_smoke_loop_then_trace`` and is mirrored by
``scripts/smoke_trace.py``.

Run: ``uv run pytest tests/test_observe.py``
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import observe
from app.agent import loop, state, tools
from app.agent.state import SessionState
from app.main import app

FIXTURE_W2 = Path(__file__).resolve().parent.parent / "fixtures" / "fake_w2.pdf"
RAW_SSN = "123456789"  # the fixture's SSN (parsed code-side; must never hit the trace)


# ---------------------------------------------------------------------------
# A tiny scripted fake LLM (same shape as tests/test_agent.py).
# ---------------------------------------------------------------------------
def _tool_call(call_id: str, name: str, args: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _resp_tools(calls: list[dict]) -> dict:
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": "", "tool_calls": calls},
            }
        ]
    }


def _resp_text(text: str) -> dict:
    return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": text}}]}


class ScriptedLLM:
    def __init__(self, responses: list[dict]):
        self._responses = list(responses)

    def __call__(self, messages, **kwargs):
        if not self._responses:
            raise AssertionError("ScriptedLLM ran out of responses")
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _clean_sessions():
    state.SESSIONS.clear()
    tools.set_guardrail_hook(tools._default_guardrail_hook)
    yield
    state.SESSIONS.clear()
    tools.set_guardrail_hook(tools._default_guardrail_hook)


# ---------------------------------------------------------------------------
# observe.record — structure + redaction at the unit level.
# ---------------------------------------------------------------------------
def test_record_appends_structured_record():
    st = SessionState(session_id="s1")
    entry = observe.record(
        st,
        "tool",
        tool_name="compute_1040",
        args={"x": 1},
        result_summary="ok refund=100",
        guardrail_verdict="allow",
        latency_ms=12.5,
    )
    assert st.trace == [entry]
    # Every F6 field is present.
    for key in ("turn", "decision", "tool", "args", "result", "guardrail_verdict", "latency_ms"):
        assert key in entry
    assert entry["turn"] == 0
    assert entry["decision"] == "tool"
    assert entry["tool"] == "compute_1040"
    assert entry["guardrail_verdict"] == "allow"
    assert entry["latency_ms"] == 12.5


def test_record_turn_index_increments():
    st = SessionState(session_id="s1")
    observe.record(st, "tool", tool_name="extract_w2")
    observe.record(st, "talk", result_summary="hello")
    assert [r["turn"] for r in st.trace] == [0, 1]
    assert [r["decision"] for r in st.trace] == ["tool", "talk"]


def test_record_redacts_ssn_in_args_and_result():
    st = SessionState(session_id="s1")
    entry = observe.record(
        st,
        "tool",
        tool_name="extract_w2",
        args={"ssn": "123-45-6789", "note": "ssn 987654321 here"},
        result_summary=f"parsed SSN {RAW_SSN} okay",
    )
    blob = json.dumps(entry)
    # The raw SSN (any separator form) must be gone from the stored record.
    assert "123-45-6789" not in blob
    assert "987654321" not in blob
    assert RAW_SSN not in blob
    # The redacted marker is present (the canonical F5 redactor masks to
    # ***-**-<last4>; the local fallback masks to ***-**-****). Either way the
    # value is masked, not the raw 9 digits.
    assert entry["args"]["ssn"].startswith("***-**-")
    assert "***-**-" in entry["result"]


def test_local_redactor_handles_separator_variants():
    for ssn in ("123-45-6789", "123 45 6789", "123456789"):
        assert observe._local_redact_ssn(f"x {ssn} y") == "x ***-**-**** y"
    # A non-SSN-shaped number is left alone.
    assert observe._local_redact_ssn("call 5551234") == "call 5551234"


def test_get_trace_returns_copy_of_records():
    st = SessionState(session_id="s1")
    observe.record(st, "talk", result_summary="hi")
    out = observe.get_trace(st)
    assert out == st.trace
    out.append({"sneaky": True})
    assert len(st.trace) == 1  # mutating the returned list does not corrupt state


# ---------------------------------------------------------------------------
# Wiring in the loop — tool / talk / refuse records are written as it runs.
# ---------------------------------------------------------------------------
def test_loop_records_tool_and_talk_decisions():
    st = state.create_session(messages=loop.initial_messages())
    st.upload_path = str(FIXTURE_W2)
    script = ScriptedLLM(
        [
            _resp_tools([_tool_call("c1", "extract_w2", {})]),
            _resp_tools([_tool_call("c2", "set_filing_status", {"filing_status": "single"})]),
            _resp_tools([_tool_call("c3", "compute_1040", {})]),
            _resp_text("All done — here is your result!"),
        ]
    )
    loop.run_turn(st, "Here's my W-2, I'm single.", llm_fn=script)

    decisions = [r["decision"] for r in st.trace]
    tools_recorded = [r["tool"] for r in st.trace if r["decision"] == "tool"]
    assert tools_recorded == ["extract_w2", "set_filing_status", "compute_1040"]
    # The final natural-language turn is recorded as a talk decision.
    assert decisions[-1] == "talk"
    talk = st.trace[-1]
    assert talk["tool"] is None
    assert "All done" in talk["result"]
    # Tool records carry a measured latency and an allow verdict.
    tool_recs = [r for r in st.trace if r["decision"] == "tool"]
    assert all(r["latency_ms"] is not None and r["latency_ms"] >= 0 for r in tool_recs)
    assert all(r["guardrail_verdict"] == "allow" for r in tool_recs)


def test_loop_records_ask_user_question_text():
    """ask_user surfaces via the tool result, so the trace must capture the text."""
    st = state.create_session(messages=loop.initial_messages())
    script = ScriptedLLM(
        [
            _resp_tools([_tool_call("c1", "ask_user", {"question": "What's your filing status?"})]),
            _resp_text("Thanks!"),
        ]
    )
    loop.run_turn(st, "let's go", llm_fn=script)
    ask_recs = [r for r in st.trace if r["tool"] == "ask_user"]
    assert ask_recs, "ask_user dispatch was not recorded"
    assert "What's your filing status?" in ask_recs[0]["result"]
    assert ask_recs[0]["args"]["question"] == "What's your filing status?"


def test_loop_records_refusal_when_guardrail_blocks():
    """A guardrail-blocked tool is recorded as decision=refuse."""

    def deny_ask(state_, name, args):
        if name == "ask_user":
            return tools.GuardrailDecision(allow=False, message="Question budget spent.")
        return tools.GuardrailDecision(allow=True)

    tools.set_guardrail_hook(deny_ask)
    st = state.create_session(messages=loop.initial_messages())
    script = ScriptedLLM(
        [
            _resp_tools([_tool_call("c1", "ask_user", {"question": "one more?"})]),
            _resp_text("No problem."),
        ]
    )
    loop.run_turn(st, "ask me something", llm_fn=script)

    refuse_recs = [r for r in st.trace if r["decision"] == "refuse"]
    assert refuse_recs, "a blocked tool was not recorded as a refusal"
    assert refuse_recs[0]["tool"] == "ask_user"
    assert refuse_recs[0]["guardrail_verdict"] == "refuse"
    assert "budget" in refuse_recs[0]["result"].lower()


def test_extract_w2_record_has_no_raw_ssn():
    """The W-2 extraction record must not leak the raw SSN anywhere."""
    st = state.create_session(messages=loop.initial_messages())
    st.upload_path = str(FIXTURE_W2)
    script = ScriptedLLM(
        [
            _resp_tools([_tool_call("c1", "extract_w2", {})]),
            _resp_text("Got your W-2!"),
        ]
    )
    loop.run_turn(st, "here's my w2", llm_fn=script)
    blob = json.dumps(st.trace)
    assert RAW_SSN not in blob
    assert "123-45-6789" not in blob


# ---------------------------------------------------------------------------
# GET /trace route — live redacted trail + 404 contract.
# ---------------------------------------------------------------------------
def test_trace_route_returns_records():
    client = TestClient(app)
    st = SessionState(session_id="route-1", messages=loop.initial_messages())
    state.SESSIONS[st.session_id] = st
    observe.record(st, "tool", tool_name="extract_w2", result_summary="ok")
    observe.record(st, "talk", result_summary="hello there")

    resp = client.get(f"/trace/{st.session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == st.session_id
    assert body["count"] == 2
    assert [r["decision"] for r in body["records"]] == ["tool", "talk"]


def test_trace_route_404_for_unknown_session():
    client = TestClient(app)
    resp = client.get("/trace/no-such-session")
    assert resp.status_code == 404


def test_trace_route_redacts_ssn():
    client = TestClient(app)
    st = SessionState(session_id="route-ssn", messages=loop.initial_messages())
    state.SESSIONS[st.session_id] = st
    observe.record(st, "tool", tool_name="extract_w2", result_summary=f"ssn {RAW_SSN}")
    resp = client.get(f"/trace/{st.session_id}")
    assert RAW_SSN not in resp.text


# ---------------------------------------------------------------------------
# observed leg (in-test smoke): a real loop turn, then GET /trace shows it.
# ---------------------------------------------------------------------------
def test_observed_smoke_loop_then_trace():
    """End-to-end: run a real loop turn, then read the live trace over HTTP.

    Mirrors scripts/smoke_trace.py: every step but the LLM is real product code —
    the loop, the tools, the trace recording, and the GET /trace route.
    """
    client = TestClient(app)
    st = SessionState(session_id="smoke", messages=loop.initial_messages())
    st.upload_path = str(FIXTURE_W2)
    state.SESSIONS[st.session_id] = st

    script = ScriptedLLM(
        [
            _resp_tools([_tool_call("c1", "extract_w2", {})]),
            _resp_tools([_tool_call("c2", "ask_user", {"question": "What's your filing status?"})]),
            _resp_tools([_tool_call("c3", "set_filing_status", {"filing_status": "single"})]),
            _resp_tools([_tool_call("c4", "compute_1040", {})]),
            _resp_text("All set — you're getting a refund!"),
        ]
    )
    # ask_user ends a turn (it waits for the user), so the answer arrives in turn 2.
    loop.run_turn(st, "Here's my W-2.", llm_fn=script)  # extract_w2 -> ask_user (turn ends)
    loop.run_turn(st, "I'm single.", llm_fn=script)  # set_filing_status -> compute_1040 -> reply

    body = client.get(f"/trace/{st.session_id}").json()
    records = body["records"]

    # Turn-by-turn: the judge can reconstruct extraction -> question -> status ->
    # compute -> warm reply from the trace alone.
    decisions = [r["decision"] for r in records]
    assert "tool" in decisions and "talk" in decisions
    tools_seen = {r["tool"] for r in records if r["tool"]}
    assert {"extract_w2", "set_filing_status", "compute_1040", "ask_user"} <= tools_seen
    assert any("filing status" in (r["result"] or "").lower() for r in records)
    # No raw SSN anywhere in the served trail.
    assert RAW_SSN not in json.dumps(body)
