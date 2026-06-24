"""F4 ``observed`` leg — a REAL multi-turn conversation against the live model.

Drives the hand-rolled agent loop (``app.agent.loop.run_turn``) against the
pinned OpenRouter model with NO mocks: it mints a session, stores
``fixtures/fake_w2.pdf`` as the session's W-2 upload, then runs a couple of real
chat turns and prints (a) the tool calls the model actually dispatched and (b)
the state the session carried across turns.

This is the F4 proof method (``observed``): confirm the agent really dispatches
``extract_w2`` / ``set_filing_status`` / ``compute_1040`` and carries state.

Run live:
    uv run python scripts/smoke_agent.py

Exit 0 + the printed evidence (tools fired across turns, W-2 + status + computed
return all present) == the observed leg passes. A non-zero exit prints the exact
blocker — do NOT fake success.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable when run as `uv run python scripts/...`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402  (path bootstrap must precede import)
from app.agent import loop  # noqa: E402
from app.agent.state import create_session  # noqa: E402

FIXTURE_W2 = Path(__file__).resolve().parent.parent / "fixtures" / "fake_w2.pdf"


def _print_turn(label: str, user_msg: str, result: loop.TurnResult) -> None:
    print(f"\n=== {label} ===")
    print(f"  user> {user_msg}")
    print(f"  tools dispatched: {result.tool_calls_made or '(none)'}")
    print(f"  assistant> {result.content.strip()[:400]}")


def run_smoke() -> dict:
    """Run the real multi-turn conversation and return an evidence summary."""
    # Fail loudly here if the key is missing — clearer than a 401 mid-loop.
    config.get_api_key()

    if not FIXTURE_W2.exists():
        raise RuntimeError(f"W-2 fixture not found at {FIXTURE_W2}")

    # 1. Mint a session and seed it (mirrors POST /session).
    state = create_session(messages=loop.initial_messages())
    # Store the fixture as the session's W-2 upload (mirrors POST /upload).
    state.upload_path = str(FIXTURE_W2)
    print(f"session minted: {state.session_id}")
    print(f"W-2 staged at: {state.upload_path}")

    all_tools: list[str] = []

    # 2. Turn 1 — user says their W-2 is uploaded. Expect extract_w2 (and likely
    #    an ask_user for filing status).
    msg1 = "I've uploaded my W-2. Can you read it and get started on my 2025 return?"
    turn1 = loop.run_turn(state, msg1)
    all_tools += turn1.tool_calls_made
    _print_turn("Turn 1 — upload + start", msg1, turn1)

    # 3. Turn 2 — user answers filing status. Expect set_filing_status, then
    #    compute_1040, then a warm natural-language result.
    msg2 = "I'm filing as single."
    turn2 = loop.run_turn(state, msg2)
    all_tools += turn2.tool_calls_made
    _print_turn("Turn 2 — filing status -> compute", msg2, turn2)

    summary = {
        "session_id": state.session_id,
        "tools_dispatched": all_tools,
        "w2_extracted": state.w2 is not None,
        "w2_wages": (state.w2.wages if state.w2 else None),
        "w2_masked_ssn": (state.w2.masked_ssn if state.w2 else None),
        "filing_status": (state.filing_status.value if state.filing_status else None),
        "computed": state.computed is not None,
        "refund": (str(state.computed.refund) if state.computed else None),
        "amount_owed": (str(state.computed.amount_owed) if state.computed else None),
        "questions_asked": state.questions_asked,
        "transcript_len": len(state.messages),
    }
    return summary


def _verify(summary: dict) -> list[str]:
    """Return a list of failures; empty == the observed criteria are met."""
    failures: list[str] = []
    fired = set(summary["tools_dispatched"])
    for required in ("extract_w2", "set_filing_status", "compute_1040"):
        if required not in fired:
            failures.append(f"tool {required!r} was never dispatched by the model")
    if not summary["w2_extracted"]:
        failures.append("W-2 was not extracted into state (state not carried)")
    if not summary["filing_status"]:
        failures.append("filing status was not set in state")
    if not summary["computed"]:
        failures.append("the return was not computed into state")
    return failures


def main() -> int:
    try:
        summary = run_smoke()
    except Exception as exc:  # noqa: BLE001 — surface the exact blocker
        print(f"\nSMOKE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("\n--- state carried across turns ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    failures = _verify(summary)
    if failures:
        print("\nSMOKE FAILED — observed criteria not met:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        "\nSMOKE PASSED — the live model dispatched extract_w2/set_filing_status/"
        "compute_1040 and the session carried the W-2, filing status, and computed "
        "return across turns."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
