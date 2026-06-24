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

## Wave 3 — F5, F6, F7 — 2026-06-24  (fast-track)

Full suite **145 passed**. Parent wired `install_guardrails()` into app startup (the F5 integration seam).

**F5 — Guardrails enforced + visible** → `proved` (test + observed): 5 code gates (on-task refusal, ≤5 turn contract, validate_return runtime invariants, redact_ssn, format_refund_owed server-template). Live smoke shows the budget refusal firing on the real route and appearing in /trace. NOTE for F10 integration: call `validate_return(state.computed)` before any PDF fill, and use `format_refund_owed(state.computed)` for the final chat number (F5 left these as integration calls, not dispatch-hook gates).
**F6 — Live observation trace** → `proved` (observed + test): observe.record at every loop decision point; GET /trace; SSN redacted at write; ask_user question text captured. 13 tests + live 7-record smoke.
**F7 — Filing-status variation** → `proved` (test + observed): hand-computed goldens per status; PDF checkbox per status; live status-change recompute. 18 tests.

**Checkpoints:** fresh-eyes reviewer SKIPPED per user time-pressure waiver (deterministic validators green; honest note). Walkthrough deferred to F10 (full integrated path not assembled until then).

## Wave 5 — F8, F9, F10 + F11 gate — 2026-06-24  (fast-track; user "keep building")

F8's builder crashed before emitting its verdict (harness StructuredOutput cap) but had written all files; parent verified from disk. Full suite **159 passed**.

**F8 — Streaming chat UI** -> `proved` (observed): live uvicorn — GET / serves the page; POST /chat/stream emits NDJSON token+done events (fetch()-over-POST, not EventSource); POST /upload sets state.upload_path; GET /trace populates; collapsible trace panel hosts F6. tests/test_ui.py in the 159.
**F9 — Warm conversation** -> `proved` (sign-off, self): live tone warm/plain/human, one question at a time, <=5 enforced by F5. User waived the user sign-off under time pressure; parent self-judged.
**F10 — End-to-end** -> `proved` (observed): parent wired the new `fill_1040_pdf` tool (validate_return gate -> fill_1040 -> state.pdf_bytes) into the registry + system prompt. scripts/smoke_e2e.py: ONE live turn ran extract_w2->set_filing_status->compute_1040->fill_1040_pdf; 771 KB filled official 2025 1040 (name + refund $238); downloadable via GET /download.
**F11 — Public deployment** -> `needs-you`: the live-URL deploy is the user's outward action (Render account + push to public GitHub). render.yaml + pip requirements.txt committed; start cmd uvicorn app.main:app --host 0.0.0.0 --port $PORT; one-command local run verified serving the full flow. Awaiting the live URL.

**Status: 11/12 proved.** The app is functionally complete and works end-to-end locally; only the public deploy (user gate) remains.

## Closeout — 12/12 proved, phase done — 2026-06-24

**Delivered:** an agentic tax-filing assistant, live at **https://taxathon.onrender.com/**. Upload a fake
W-2 → warm ≤5-question chat → download a completed **official 2025 Form 1040** (verified $238 refund). All
four pillars enforced + visible; 159 tests green; deterministic tax math + official-PDF fill + live trace.

**Closeout gate (all passed against the final tree):** re-ran the verification command (159 passed);
re-observed every observed-proof feature (F4/F6/F7/F8/F10/F11/F12) on the real route — incl. the live Render
URL streaming the flow and F7's single→HoH recompute (refund 238→1240); whole-product walkthrough
(upload→chat→download) passed locally and live. Evidence under `.kodos/evidence/`.

**Front door refreshed:** README.md (live URL + run/verify/deploy), DECISIONS.md (half-page note),
IMPLEMENTATION.md (rendered snapshot).

**Caveats:** v1 scope — single W-2, fake data, not tax advice; image/OCR upload, MFJ/MFS spouse-identity
fields, and extra credit lines are out of scope. Money-cell pixel alignment in the PDF is "values correct +
legible," not pixel-perfect (research caveat).

**Process notes for next time (learnings store capture deferred under the time waiver):** (1) a builder can
crash on the StructuredOutput verdict cap *after* doing the work — reconcile from disk, not the verdict.
(2) Strict per-builder file ownership + a single shared-file editor per wave kept the parallel fan-out
collision-free. (3) Greenfield needs a serial substrate scaffold before fanning out builders.

## Post-closeout fix — ask_user questions now render in chat — 2026-06-24

Bug found in live use: the agent's `ask_user` questions appeared in `/trace` but not the chat window.
Root cause: `ask_user` was dispatched like any tool (loop continued; the model returned empty NL content),
so the turn's reply was empty and only the trace captured the question. Fix (`app/agent/loop.py`):
`ask_user` now ENDS the turn and its question becomes the reply (correct "pause and wait for the user"
semantics). Updated two tests that had encoded the old behavior. Verified on the real HTTP /chat/stream
route (question streams to the user) + 159 tests green. Also added `mock_w2s/` + `scripts/gen_mock_w2s.py`
(varied test W-2s in the app's AcroForm format).
