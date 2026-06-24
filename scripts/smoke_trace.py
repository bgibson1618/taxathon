"""F6 ``observed`` leg — a real loop turn, then GET /trace shows the records.

Drives one full agent turn (extract_w2 -> ask_user -> set_filing_status ->
compute_1040 -> warm reply) through the REAL ``app.agent.loop.run_turn`` and the
REAL ``GET /trace/{session_id}`` route, then prints the turn-by-turn trace the
judge would watch live. The LLM is a small scripted fake so the smoke is
deterministic and needs no network/API key — but every *other* step (the loop, the
tools, the trace recording, the HTTP route) is the real product code.

This is the F6 proof method (``observed``): confirm that running a flow populates
``/trace`` turn-by-turn with structured records (tool / talk / refuse), and that
SSN-shaped values are redacted in the trail.

Run:
    uv run python scripts/smoke_trace.py

Exit 0 + the printed trace (tool dispatches, the ask_user question, the talk turn,
a refusal, no raw SSN) == the observed leg passes. A non-zero exit prints the exact
blocker — do NOT fake success.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the project root importable when run as `uv run python scripts/...`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.agent import loop, state, tools  # noqa: E402
from app.agent.state import SessionState  # noqa: E402
from app.main import app  # noqa: E402

FIXTURE_W2 = Path(__file__).resolve().parent.parent / "fixtures" / "fake_w2.pdf"


# --- a tiny scripted fake LLM (same shape as tests/test_agent.py) ----------
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


def run_smoke() -> dict:
    """Run a full scripted turn through run_turn, then read GET /trace."""
    state.SESSIONS.clear()
    tools.set_guardrail_hook(tools._default_guardrail_hook)

    if not FIXTURE_W2.exists():
        raise RuntimeError(f"W-2 fixture not found at {FIXTURE_W2}")

    # Register a session in the SAME registry the HTTP route reads.
    st = SessionState(session_id="smoke-trace", messages=loop.initial_messages())
    st.upload_path = str(FIXTURE_W2)
    state.SESSIONS[st.session_id] = st

    # A scripted flow that exercises tool / talk decision points, including the
    # ask_user question that must surface in the trace.
    script = ScriptedLLM(
        [
            _resp_tools([_tool_call("c1", "extract_w2", {})]),
            _resp_tools([_tool_call("c2", "ask_user", {"question": "What's your filing status?"})]),
            _resp_tools([_tool_call("c3", "set_filing_status", {"filing_status": "single"})]),
            _resp_tools([_tool_call("c4", "compute_1040", {})]),
            _resp_text("All set! You're getting a refund. Want me to fill your 1040?"),
        ]
    )
    loop.run_turn(st, "Here's my W-2 — I'm single.", llm_fn=script)

    # A separate refusal turn: a guardrail blocks ask_user (budget spent), which the
    # trace records as decision=refuse.
    def deny_ask(state_, name, args):
        if name == "ask_user":
            return tools.GuardrailDecision(allow=False, message="Question budget spent.")
        return tools.GuardrailDecision(allow=True)

    tools.set_guardrail_hook(deny_ask)
    refuse_script = ScriptedLLM(
        [
            _resp_tools([_tool_call("c5", "ask_user", {"question": "one more?"})]),
            _resp_text("No worries — let's keep going with what we have."),
        ]
    )
    loop.run_turn(st, "Can I ask something off topic?", llm_fn=refuse_script)
    tools.set_guardrail_hook(tools._default_guardrail_hook)

    # Now read the trace through the REAL HTTP route the judge/UI uses.
    client = TestClient(app)
    resp = client.get(f"/trace/{st.session_id}")
    if resp.status_code != 200:
        raise RuntimeError(f"GET /trace returned {resp.status_code}: {resp.text}")
    body = resp.json()

    # 404 contract check on an unknown session.
    missing = client.get("/trace/does-not-exist")
    if missing.status_code != 404:
        raise RuntimeError(f"GET /trace for unknown session should 404, got {missing.status_code}")

    return {
        "raw_ssn": st.w2._ssn if st.w2 else None,
        "trace_body": body,
    }


def _print_trace(records: list[dict]) -> None:
    print("\n=== live /trace (turn-by-turn) ===")
    for r in records:
        line = f"  #{r['turn']:>2} {r['decision']:<7}"
        if r.get("tool"):
            line += f" tool={r['tool']}"
        if r.get("guardrail_verdict"):
            line += f" verdict={r['guardrail_verdict']}"
        if r.get("result"):
            line += f"  -> {r['result'][:70]}"
        print(line)


def _verify(summary: dict) -> list[str]:
    failures: list[str] = []
    body = summary["trace_body"]
    records = body.get("records", [])
    decisions = [r["decision"] for r in records]
    tools_seen = {r.get("tool") for r in records}

    if not records:
        failures.append("trace was empty — no records populated")
    if "tool" not in decisions:
        failures.append("no 'tool' decision recorded")
    if "talk" not in decisions:
        failures.append("no 'talk' decision recorded")
    if "refuse" not in decisions:
        failures.append("no 'refuse' decision recorded")
    for expected_tool in ("extract_w2", "set_filing_status", "compute_1040"):
        if expected_tool not in tools_seen:
            failures.append(f"tool {expected_tool!r} missing from trace")

    # The ask_user question text must surface in the trace (F4/F6 note).
    if not any("filing status" in (r.get("result") or "").lower() for r in records):
        failures.append("ask_user question text did not surface in the trace")

    # SSN redaction: the raw SSN must never appear anywhere in the trail.
    raw = summary.get("raw_ssn")
    blob = json.dumps(body)
    if raw and raw in blob:
        failures.append("RAW SSN leaked into the trace (redaction failed)")
    return failures


def main() -> int:
    try:
        summary = run_smoke()
    except Exception as exc:  # noqa: BLE001 — surface the exact blocker
        print(f"\nSMOKE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    body = summary["trace_body"]
    print(f"session: {body.get('session_id')}  records: {body.get('count')}")
    _print_trace(body.get("records", []))

    failures = _verify(summary)
    if failures:
        print("\nSMOKE FAILED — observed criteria not met:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        "\nSMOKE PASSED — a real loop turn populated /trace turn-by-turn with "
        "tool/talk/refuse records (ask_user question captured), and the SSN is "
        "redacted in the trail."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
