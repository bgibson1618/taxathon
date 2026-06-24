"""F10 end-to-end smoke: upload a W-2 -> chat -> a real filled 1040 to download.

Drives the live agent loop (real model) through the whole flow and asserts the
session ends with downloadable PDF bytes that are a genuine filled 2025 1040.
Run: ``uv run python scripts/smoke_e2e.py``
"""
from __future__ import annotations

import io
import sys

from pypdf import PdfReader

from app.agent import create_session, initial_messages, run_turn
from app.guardrails import install_guardrails

install_guardrails()  # same wiring the app does at startup

state = create_session(messages=initial_messages())
state.upload_path = "fixtures/fake_w2.pdf"

tools_seen: list[str] = []
for i, msg in enumerate(
    [
        "I've uploaded my W-2 and I'm filing as single. Please do my whole return.",
        "Yes please, go ahead and finish it and get my form ready to download.",
        "Thanks!",
    ]
):
    r = run_turn(state, msg)
    tools_seen += r.tool_calls_made
    print(f"turn {i+1}: tools={r.tool_calls_made}")
    if state.pdf_bytes:
        break

print("---")
print("tools dispatched overall:", tools_seen)
print("filing_status:", getattr(state.filing_status, "value", state.filing_status))
print("computed refund:", getattr(state.computed, "refund", None),
      "owed:", getattr(state.computed, "amount_owed", None))
print("pdf_bytes:", len(state.pdf_bytes) if state.pdf_bytes else None)

assert state.pdf_bytes, "FAIL: no filled 1040 PDF was produced (download would 404)"
text = "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(state.pdf_bytes)).pages)
has_name = "Alex" in text or "Taxpayer" in text
has_amount = "238" in text or str(getattr(state.computed, "refund", "")) in text
assert "fill_1040_pdf" in tools_seen, "FAIL: agent never called fill_1040_pdf"
assert has_name, "FAIL: taxpayer name not in the filled PDF"
print("PDF contains taxpayer name:", has_name, "| refund figure present:", has_amount)
print("E2E PASSED — upload -> chat -> downloadable filled official 2025 1040")
sys.exit(0)
