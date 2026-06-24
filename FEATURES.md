# FEATURES — Taxathon

The feature ledger **spec** — what this project must deliver, each feature with success criteria, a
proof method, and dependencies. Per the KodOS model, **state** (status / attempts / evidence) lives
in `.kodos/state.json`, not here; this file is read-only during a build.

**Feature** = the smallest user-meaningful capability that can be independently proved.
**Proof methods:** `test` (automated), `observed` (agent runs it and watches the behavior),
`sign-off` (human confirms). Flat ids; `depends_on` drives build order and parallelism.

Grounded in `ARCHITECTURE.md` ("Deterministic Spine, Agentic Skin"). **v1 scope only** — stretch
items (LLM-vision W-2 cross-check, non-AcroForm / image W-2 uploads, MFJ/MFS spouse-identity PDF
fields, best-effort credit lines) are deliberately out of this ledger per the architecture's Key
Decisions; the PRD/NFR are aligned to the same boundary.

---

## F1 — 2025 tax computation engine
- **Proof:** `test` (golden cases per filing status match independent hand-computed 2025 figures)
- **Depends on:** —

**Functionality:** Given W-2 wages, federal withholding, and a filing status, the system computes the
correct 2025 Form 1040 result — standard deduction, taxable income, bracket tax, and the resulting
refund or amount owed — entirely in deterministic code. The LLM never does arithmetic.

**Success criteria**
- For the fixture profile (single filer, ~$40k W-2), the computed refund/owed matches an independently
  hand-computed 2025 figure to the dollar.
- All four filing statuses (Single, MFJ, MFS, HoH) apply the correct 2025 standard deduction and
  bracket tax, each checked against an independent golden value (not a same-path recompute).
- Bracket-boundary and zero-tax cases compute correctly (taxable income floored at 0).
- The 2025 constants (standard deductions, brackets) are transcribed from official IRS figures with the
  source cited in code.

## F2 — W-2 ingest (deterministic parse)
- **Proof:** `test` (parsing the supplied fixture yields the expected fields; SSN never appears in logs/trace)
- **Depends on:** —

**Functionality:** A user uploads a (fake) W-2 file and the agent reads it into validated structured
fields — wages, federal withholding, and taxpayer identity (name, address, SSN) — deterministically,
with the SSN handled code-side and masked everywhere it could leak.

**Success criteria**
- Uploading the supplied fake W-2 yields the exact expected wages, withholding, and identity fields.
- Out-of-range or inconsistent values (e.g. withholding > wages) are rejected by validation before use.
- The SSN is masked in all logs and the observation trace, and the raw SSN never appears in an LLM prompt.
- A realistic fake W-2 fixture for a ~$40k earner exists in the repo and parses cleanly.

## F3 — Filled official 2025 1040 PDF + download
- **Proof:** `test` (mapped identity + numeric fields populate; values present in extracted page text) + `sign-off` (a human confirms it reads as a genuinely completed 1040 in a viewer)
- **Depends on:** F1, F2

**Functionality:** Once the return is computed, the user can download a completed **official IRS 2025
Form 1040 PDF** with both taxpayer identity (name, address, SSN, filing status) and the computed lines
filled in.

**Success criteria**
- The downloaded file is the official 2025 1040, flattened, with identity and computed numeric lines
  populated — values present in the PDF's extracted page text.
- Every field name the fill maps still exists in the vendored form (guards against an IRS re-post).
- A human opens the flattened PDF in a standard viewer and confirms it reads as a genuinely completed,
  legible 1040 (placement acceptable) — sign-off.

## F4 — Agent chat loop + tool dispatch + state
- **Proof:** `observed` (a multi-turn conversation drives real tool calls and carries state across turns on the real `/chat` route)
- **Depends on:** F1, F2, F12

**Functionality:** The user has a multi-turn conversation in which the agent carries context across
turns, decides which tool to call, and the server runs that tool in plain Python — the chat-loop and
tools pillars working together.

**Success criteria**
- Across turns the agent remembers earlier answers (e.g. references the uploaded W-2 and a filing status
  given earlier) — state is carried, not re-derived.
- The agent selects and dispatches real tools (`extract_w2`, `set_filing_status`, `compute_1040`),
  each doing real work, observed in the running app on the real route. (`fill_1040_pdf` is proved by F3
  and exercised end-to-end in F10.)
- Malformed tool arguments are rejected before any tool code runs.
- The loop terminates cleanly (no infinite tool loop) and retries a transient LLM error once.

## F5 — Guardrails: enforced + visible
- **Proof:** `test` (each gate unit-tested) + `observed` (refusal and budget fire visibly in the live trace)
- **Depends on:** F1, F4

**Functionality:** The agent stays bounded by guardrails enforced in code (not prompt text) and visible
to a judge: it asks no more than 5 questions, refuses off-task / tax-advice requests, and never lets a
fabricated number reach the form.

**Success criteria**
- The ≤5-question budget is enforced by counting `ask_user` tool calls (≤5); questions reach the user
  only through `ask_user`, and the final natural-language turn is prompt-guided + server-templated not to
  ask. (The greeting and W-2 upload prompts do not count; a recovery re-ask does.)
- An off-task or tax-advice request triggers a canned refusal that short-circuits the loop and appears as
  a `decision: refuse` record in the live trace.
- The no-fabrication gate runs `validate_return` — internal-consistency invariants (refund/owed ==
  payments − total tax; taxable income ≥ 0; recompute matches `state.computed`) — before any PDF fill; an
  inconsistent value is blocked from reaching the form. (Correctness vs published IRS figures is F1's
  golden test, separate from this runtime gate.)
- The refund/owed amount in the final chat message is **server-templated from `state.computed`**, so the
  LLM cannot misstate the number in prose.
- Each guardrail decision is written to the trace with its verdict.

## F6 — Live observation trace
- **Proof:** `observed` (the trace populates live on the real route as the agent runs) + `test` (records written; SSN redacted)
- **Depends on:** F4

**Functionality:** A judge can watch what the agent did and why, live, while it runs — every decision,
tool call, and guardrail verdict is recorded and viewable at `/trace` and in a collapsible UI panel.

**Success criteria**
- Running a real flow populates the `/trace` view and the UI panel turn-by-turn while it runs, so a judge
  can reconstruct the agent's decisions and actions as they happen.
- Every decision point (talk / tool / refuse) writes a structured record (turn, decision, tool, redacted
  args, result, guardrail verdict).
- SSN-shaped values are redacted in every trace record.

## F7 — Filing-status variation
- **Proof:** `test` (recompute correct per status) + `observed` (the change-status flow visibly recomputes on the real route)
- **Depends on:** F1, F3, F4

**Functionality:** The user can state or change their filing status mid-conversation and see the standard
deduction, tax, and resulting return recompute and refill accordingly — across all four statuses.

**Success criteria**
- Changing filing status recomputes the standard deduction and tax correctly for each of Single / MFJ /
  MFS / HoH, each checked against a golden value.
- In the running app, changing status mid-chat visibly updates the result and the trace shows the recompute.
- Single and HoH produce a fully-filled PDF; MFJ/MFS produce correct computed figures (spouse-identity
  PDF fields are out of v1 scope).

## F8 — Streaming chat UI + minimal web page
- **Proof:** `observed` (tokens stream and a working indicator shows during tool turns, on the real route)
- **Depends on:** F4, F6

**Functionality:** The user interacts through a minimal web chat page where the assistant's replies stream
in, tool-running turns show a working indicator (no dead air), and they can upload the W-2 and download
the result.

**Success criteria**
- The final assistant turn streams progressively in the browser via a `fetch()` stream (not `EventSource`),
  with the byte stream buffered and split on newlines so partial NDJSON chunks never break rendering.
- Tool-running turns show a working/typing indicator, so the user sees it is working rather than dead air.
- The page supports W-2 file upload, message send, a cold-start "waking up" hint, and **hosts the
  collapsible trace panel delivered by F6** (F6 owns the trace; F8 renders it on the page).
- Basic accessibility per NFR: the full path (type + Enter to send, upload, download) is keyboard-usable,
  text has readable contrast and legible default size, and the typing indicator respects reduced-motion.

## F9 — Warm, human conversation
- **Proof:** `sign-off` (a human confirms the conversation feels warm, clear, and human within the budget)
- **Depends on:** F4, F5, F8

**Functionality:** The conversation feels warm and human — friendly, clear, plain-language, one question
at a time — not robotic or interrogative, within the ≤5-question budget.

**Success criteria**
- A human runs the full conversation and confirms it feels warm, clear, and reassuring — like a helpful
  person, not a form (the user's own words: "warm and human — friendly, clear, not robotic or interrogative").
- Questions are asked one at a time in plain language, with no jargon, within the ≤5-question budget.
- Error and recovery messages read as calm and guiding, not blunt.

## F10 — End-to-end filing flow
- **Proof:** `observed` (real fake W-2 in → downloadable filled 1040 out, via the chat, on the real product route, no mocked step)
- **Depends on:** F3, F5, F6, F8, F9

**Functionality:** The whole journey works end to end on the real product route: a user uploads the fake
W-2, has the warm ≤5-question chat, and downloads a completed 2025 Form 1040 — exactly the user's stated win.

**Success criteria**
- On the real route, uploading the fake W-2 and completing the chat yields a downloadable, correctly-filled
  official 2025 1040 — not a happy-path mock of a single step (the user's own words: "a real, downloadable
  1040 ... proof it works end-to-end").
- The full run is reflected in the live trace (extraction → questions → compute → no-fabrication gate →
  fill), demonstrating all four pillars in one flow.
- The downloaded return's refund/owed matches the engine's computation for the fixture.

## F11 — Public deployment + local fallback
- **Proof:** `observed` (the live public URL responds and serves the flow; one-command local run works)
- **Depends on:** F7, F9, F10

**Functionality:** The system is reachable by a judge at a public URL and can also be run locally with one
command as a fallback.

**Success criteria**
- The app is deployed to a public URL (Render or comparable) that loads the chat and serves the end-to-end
  flow; a "waking up" hint covers cold start.
- A documented one-command local run (`uv run uvicorn app.main:app ...`) starts the app and serves the same
  flow.
- The repo contains the source, the fake W-2 fixture, and the vendored official 2025 1040 PDF.
- A short `DECISIONS` note (≈ half a page) covering the open-item choices is present in the repo
  (the build-time deliverable; seeded from `DECISION_LOG.md`).

## F12 — Model + environment preflight
- **Proof:** `test` (env loads; tool-call smoke test passes) + `observed` (one real tool-call round-trip on the pinned OpenRouter route)
- **Depends on:** —

**Functionality:** Before the agent loop is built on it, the project confirms its single external
dependency works: the OpenRouter model is pinned (with a fallback), the API key actually loads, and the
model reliably performs tool-calling on our route — so "does it actually work" doesn't fail late on an
unverified assumption.

**Success criteria**
- `OPENROUTER_API_KEY` loads from `.env` under both `uv run uvicorn ...` and `uv run pytest` (e.g. via
  `python-dotenv` / `load_dotenv()`); a missing key fails loudly with a clear message, not a silent `None`.
- A pinned primary model id and a documented fallback id are recorded in config; both are filtered for
  `supported_parameters=tools`.
- A minimal smoke test issues one real tool-calling request to the pinned model and gets back a
  well-formed tool call (proving the route supports the loop's tool-calling before F4 relies on it).

---

**Dependency graph:** **F12 (model + env preflight), F1 (tax engine), and F2 (W-2 ingest) are independent
roots** and parallelize immediately. **F3 (PDF fill)** depends on F1+F2; **F4 (agent loop)** depends on
F1+F2+F12 (it can't be honestly built until tool-calling is verified). Off F4, a wide parallel fan:
**F5 (guardrails)** (also F1), **F6 (trace)**, and **F7 (filing-status variation)** (also F1+F3); **F8
(streaming UI)** depends on F4+F6 (it hosts F6's trace panel). **F9 (warm conversation, sign-off)** depends
on F4+F5+F8. **F10 (end-to-end)** is the convergence, depending on F3+F5+F6+F8+F9. **F11 (deployment +
readiness)** depends on F7+F9+F10, so it can't ship before filing-status variation and the conversation
sign-off are complete. Critical path: F12/F1/F2 → F4 → F5/F6/F8 → F9 → F10 → F11; F3 and F7 ride alongside.
