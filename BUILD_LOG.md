# Build Log — Taxathon

Append-only journal of the KodOS build (F16). Parent-written; one entry per wave/feature.

---

## Wave 1 — F1, F2, F12 (roots) — 2026-06-24

Substrate established first (uv project, FastAPI skeleton, `uv run pytest` green, official 2025 1040
vendored at `assets/f1040_2025.pdf` — 2 pages, 229 fields, verified TY2025/no-DRAFT). Three independent
roots built concurrently by parallel `implementer` agents; reconciled by independent re-run (full suite
**39 passed**).

**F1 — 2025 tax computation engine** → `proved` (test)
- Route: frozen dataclass `ComputedReturn`; `FilingStatus` str-Enum as a reusable token; Decimal whole-dollar ROUND_HALF_UP.
- Decisions: constants cite Rev. Proc. 2024-40 inline; golden cases checked against independent hand-computed literals + a from-scratch bracket-walk cross-check (not a same-path recompute); taxable floored at 0; refund XOR owed.
- Proof: `uv run pytest tests/test_tax.py` → 18 passed (re-run in full suite; cross-check matched all goldens).

**F2 — W-2 ingest (deterministic parse)** → `proved` (test)
- Route: pypdf-only fixture (content-stream labels + named AcroForm fields) parsed deterministically into a frozen pydantic `W2`; raw SSN in a private attr, only `masked_ssn` exposed; single `W2ValidationError` wrapper.
- Decisions: fixture data clearly fake (Alex Taxpayer, SSN 123-45-6789, wages 40000, withholding 3000); reportlab not installed so PDF built with pypdf alone; field names + expected values centralized so builder/parser can't drift.
- Proof: `uv run pytest tests/test_w2.py` → 15 passed; raw SSN never leaks in repr/model_dump (asserted).
- Concern (raised by builder, **resolved at reconcile**): pydantic was only a FastAPI transitive dep → parent pinned `pydantic>=2` in `pyproject.toml`.

**F12 — model + environment preflight** → `proved` (test + observed)
- Route: `config.py` (env load + fail-loud key + tools-filtered model ids) + `llm.py` (httpx OpenAI-compatible client, `require_parameters` routing) + live smoke test.
- Decisions: PRIMARY `anthropic/claude-sonnet-4.6`, FALLBACK `anthropic/claude-sonnet-4.5` — both selected by querying OpenRouter `/models` and keeping Anthropic Claude models with `tools` in `supported_parameters`; smoke uses `tool_choice:"required"` to force a deterministic round-trip.
- Proof: `uv run pytest tests/test_config.py` → 5 passed (test leg); `uv run python scripts/smoke_tools.py` → exit 0, well-formed live `tool_call` from the pinned model (observed leg, **independently re-run by parent**).

**Checkpoints:**
- Drift (F20): deterministic validators green (state valid, scheduler resolves). Fresh-eyes reviewer **deferred** — wave 1 is isolated root modules, nothing integrated yet (bounded deferral 1 of max 2; will run by the first integration wave).
- Walkthrough (F36): no-op — no integrated user path assembled yet.

## Wave 2 — F3, F4 — 2026-06-24  (fast-track: user waived deep ceremony)

Full suite re-run **77 passed**.

**F3 — Filled official 2025 1040 PDF** → `proved` (test + sign-off [self])
- Route: discovered AcroForm field names by /Rect Y-position vs extracted line labels (tooltips absent); validated sentinel fills survive flatten; on-value `/1` for filing-status checkbox.
- Proof: `uv run pytest tests/test_pdf.py` 15 passed; parent rendered the sample to PNG and eyeballed a genuine populated 2025 1040 (refund $238). Sign-off self-accepted (user waived); money-cell pixel alignment per research caveat.

**F4 — Agent chat loop + tools + state** → `proved` (observed)
- Route: hand-rolled `while finish_reason=='tool_calls'` loop; tiny JSON-schema-subset arg validator; tool callables mutate SessionState (LLM never authors a number); guardrail no-op seam for F5; injectable llm_fn for mocked unit tests.
- Proof: `scripts/smoke_agent.py` live — dispatched extract_w2/set_filing_status/compute_1040, carried state across turns, refund $238; `uv run pytest tests/test_agent.py` 23 passed.
- Seams for later: ask_user question surfaces via tool result not NL prose (F8 must render it); ≤5 budget cap + question_turn_contract are F5's (hook installed).

**Checkpoints:** fresh-eyes reviewer deferred (2 of max 2 — MUST run next wave); walkthrough no-op (no full integrated path yet).
