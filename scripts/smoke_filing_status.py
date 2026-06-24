"""F7 ``observed`` leg — a REAL conversation that CHANGES filing status mid-flow.

Drives the hand-rolled agent loop (``app.agent.loop.run_turn``) against the pinned
OpenRouter model with NO mocks. It mints a session, stages ``fixtures/fake_w2.pdf``
as the W-2 upload, then:

  1. Turn 1 — user says the W-2 is uploaded  -> model calls ``extract_w2``
     (and typically ``ask_user`` for filing status).
  2. Turn 2 — user says "single"             -> ``set_filing_status`` + ``compute_1040``.
     We snapshot the BEFORE return (standard deduction / tax / refund).
  3. Turn 3 — user says "actually, head of household" -> ``set_filing_status`` +
     ``compute_1040`` AGAIN, on the SAME carried W-2. We snapshot the AFTER return.

The proof is that the standard deduction, tax, and refund **visibly recompute** across
the change — single (std 15,000; tax 2,762; refund 238) -> head_of_household
(std 22,500; tax 1,760; refund 1,240) — while the W-2 wages/withholding the session
carries are unchanged. That is F7: state is carried; only the status varies; the result
recomputes.

This is the F7 ``observed`` proof method. Run live:

    uv run python scripts/smoke_filing_status.py

Exit 0 + the printed before/after table == the observed leg passes. A non-zero exit
prints the exact blocker — do NOT fake success.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Make the project root importable when run as `uv run python scripts/...`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402  (path bootstrap must precede import)
from app.agent import loop  # noqa: E402
from app.agent.state import SessionState, create_session  # noqa: E402
from app.tax.constants_2025 import FilingStatus  # noqa: E402

FIXTURE_W2 = Path(__file__).resolve().parent.parent / "fixtures" / "fake_w2.pdf"


@dataclass(frozen=True)
class StatusSnapshot:
    """The computed figures captured after a status is set in the live conversation."""

    filing_status: Optional[str]
    standard_deduction: Optional[str]
    tax: Optional[str]
    refund: Optional[str]
    amount_owed: Optional[str]

    @classmethod
    def of(cls, state: SessionState) -> "StatusSnapshot":
        c = state.computed
        return cls(
            filing_status=(state.filing_status.value if state.filing_status else None),
            standard_deduction=(str(c.standard_deduction) if c else None),
            tax=(str(c.tax) if c else None),
            refund=(str(c.refund) if c else None),
            amount_owed=(str(c.amount_owed) if c else None),
        )


def _print_turn(label: str, user_msg: str, result: loop.TurnResult) -> None:
    print(f"\n=== {label} ===")
    print(f"  user> {user_msg}")
    print(f"  tools dispatched: {result.tool_calls_made or '(none)'}")
    print(f"  assistant> {result.content.strip()[:400]}")


def run_smoke() -> dict:
    """Run the real change-status conversation and return an evidence summary."""
    # Fail loudly here if the key is missing — clearer than a 401 mid-loop.
    config.get_api_key()

    if not FIXTURE_W2.exists():
        raise RuntimeError(f"W-2 fixture not found at {FIXTURE_W2}")

    # 1. Mint a session and stage the W-2 (mirrors POST /session + POST /upload).
    state = create_session(messages=loop.initial_messages())
    state.upload_path = str(FIXTURE_W2)
    print(f"session minted: {state.session_id}")
    print(f"W-2 staged at: {state.upload_path}")

    all_tools: list[str] = []

    # Turn 1 — upload + start. Expect extract_w2 (and likely an ask_user).
    msg1 = "I've uploaded my W-2. Can you read it and get started on my 2025 return?"
    turn1 = loop.run_turn(state, msg1)
    all_tools += turn1.tool_calls_made
    _print_turn("Turn 1 — upload + start", msg1, turn1)

    # Turn 2 — set status to single. Expect set_filing_status -> compute_1040.
    msg2 = "I'm filing as single."
    turn2 = loop.run_turn(state, msg2)
    all_tools += turn2.tool_calls_made
    _print_turn("Turn 2 — status = single -> compute", msg2, turn2)
    before = StatusSnapshot.of(state)
    # Carry-check: capture the W-2 the session is holding so we can prove it is unchanged.
    w2_wages_before = state.w2.wages if state.w2 else None
    w2_wh_before = state.w2.fed_withholding if state.w2 else None

    # Turn 3 — CHANGE status to head of household. Expect set_filing_status ->
    # compute_1040 AGAIN, recomputing on the same carried W-2.
    msg3 = "Actually, I need to change that — I'm head of household, not single. Please redo it."
    turn3 = loop.run_turn(state, msg3)
    all_tools += turn3.tool_calls_made
    _print_turn("Turn 3 — CHANGE status -> head_of_household -> recompute", msg3, turn3)
    after = StatusSnapshot.of(state)

    summary = {
        "session_id": state.session_id,
        "tools_dispatched": all_tools,
        "w2_wages": (state.w2.wages if state.w2 else None),
        "w2_withholding": (state.w2.fed_withholding if state.w2 else None),
        "w2_wages_before": w2_wages_before,
        "w2_withholding_before": w2_wh_before,
        "before": before,
        "after": after,
    }
    return summary


def _verify(summary: dict) -> list[str]:
    """Return a list of failures; empty == the observed F7 criteria are met."""
    failures: list[str] = []
    before: StatusSnapshot = summary["before"]
    after: StatusSnapshot = summary["after"]

    # The model must have actually set BOTH statuses and computed each time.
    fired = summary["tools_dispatched"]
    if fired.count("set_filing_status") < 2:
        failures.append(
            f"set_filing_status fired {fired.count('set_filing_status')}x; "
            "the change-status flow needs it twice (single, then head_of_household)"
        )
    if fired.count("compute_1040") < 2:
        failures.append(
            f"compute_1040 fired {fired.count('compute_1040')}x; the return must "
            "recompute after the status change"
        )

    # The session ended on head_of_household with a fresh computation.
    if after.filing_status != FilingStatus.HEAD_OF_HOUSEHOLD.value:
        failures.append(
            f"final filing status is {after.filing_status!r}, expected head_of_household"
        )

    # The figures must have VISIBLY recomputed across the change.
    if before.standard_deduction == after.standard_deduction:
        failures.append(
            f"standard deduction did not change ({before.standard_deduction}); "
            "status change did not recompute the deduction"
        )
    if before.tax == after.tax:
        failures.append(f"tax did not change ({before.tax}); status change did not recompute tax")
    if before.refund == after.refund:
        failures.append(
            f"refund did not change ({before.refund}); status change did not recompute refund"
        )

    # The carried W-2 (wages/withholding) must be UNCHANGED — only the status varied.
    if summary["w2_wages"] != summary["w2_wages_before"]:
        failures.append("W-2 wages changed across the status change (state not carried cleanly)")
    if summary["w2_withholding"] != summary["w2_withholding_before"]:
        failures.append("W-2 withholding changed across the status change (state not carried cleanly)")

    # And each side must match the F1 deterministic goldens (single / HoH) so the
    # recompute is correct, not merely different.
    expected_before = ("single", "15000", "2762", "238")
    expected_after = ("head_of_household", "22500", "1760", "1240")
    got_before = (
        before.filing_status,
        before.standard_deduction,
        before.tax,
        before.refund,
    )
    got_after = (after.filing_status, after.standard_deduction, after.tax, after.refund)
    if got_before != expected_before:
        failures.append(f"BEFORE figures {got_before} != golden single {expected_before}")
    if got_after != expected_after:
        failures.append(f"AFTER figures {got_after} != golden head_of_household {expected_after}")

    return failures


def main() -> int:
    try:
        summary = run_smoke()
    except Exception as exc:  # noqa: BLE001 — surface the exact blocker
        print(f"\nSMOKE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    before: StatusSnapshot = summary["before"]
    after: StatusSnapshot = summary["after"]

    print("\n--- filing status CHANGED mid-conversation (state carried) ---")
    print(f"  W-2 carried unchanged: wages={summary['w2_wages']} withholding={summary['w2_withholding']}")
    print(f"  tools dispatched (all turns): {summary['tools_dispatched']}")
    print()
    header = f"  {'figure':<22}{'BEFORE (single)':>20}{'AFTER (head_of_household)':>28}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    rows = [
        ("filing_status", before.filing_status, after.filing_status),
        ("standard_deduction", before.standard_deduction, after.standard_deduction),
        ("tax", before.tax, after.tax),
        ("refund", before.refund, after.refund),
    ]
    for name, b, a in rows:
        print(f"  {name:<22}{str(b):>20}{str(a):>28}")

    failures = _verify(summary)
    if failures:
        print("\nSMOKE FAILED — observed F7 criteria not met:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        "\nSMOKE PASSED — the live model set filing status to single, then CHANGED it to "
        "head_of_household, and the standard deduction (15,000 -> 22,500), tax "
        "(2,762 -> 1,760), and refund (238 -> 1,240) visibly recomputed on the same "
        "carried W-2."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
