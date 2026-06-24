# Architecture — Taxathon

## Role
System shape and technical intent for the Taxathon agentic tax-filing assistant — what it is, how
it's built, and which choices are locked vs. still open. Grounded in `PRD.md` (what we're building)
and `NFR_UX.md` (how it must behave / feel). Designed via a 3-angle design panel, synthesized, then
**adversarially verified across three model backends (Claude + Codex + Gemini/antigravity)**; the
cross-backend pass caught five concrete defects that are folded in below (see **Key Decisions**).

## Overview
A single **FastAPI** app (Python 3.12 via `uv`, Uvicorn) serving one minimal static chat page plus a
small JSON/stream API, deployed on Render free tier. The brain is a **hand-rolled agent loop** over
OpenRouter's OpenAI-compatible Chat Completions endpoint: the LLM is given a typed tool registry,
picks a tool, the server runs it in plain Python, and re-calls until the model emits a natural-
language turn that is **streamed to the browser**. The organizing idea: **every correctness- and
output-bearing step is deterministic Python the LLM cannot flake** — W-2 read, 2025 tax math, PDF
fill, the ≤5-question gate, and refusals — so the LLM owns only conversation phrasing and tool
selection; it never owns a number, a refusal verdict, or the filled form. The four pillars are each
a small, named, individually-testable module, with a live `/trace` endpoint + UI panel making the
agent's decisions watchable in the running system.

## Components
| Component | Responsibility | Notes |
| --- | --- | --- |
| `app/main.py` | FastAPI surface only (no business logic): `GET /` (chat page), `POST /session` (mint session_id + greeting), `POST /upload` (W-2 → extract → store; spends **zero** questions), `POST /chat` (run one agent turn; **streamed** response), `GET /trace/{sid}` (live redacted trace), `GET /download/{sid}` (filled 1040 PDF) | Streaming is a **`fetch()` ReadableStream over POST (NDJSON)**, *not* `EventSource` — EventSource is GET-only and cannot carry the chat body (cross-backend defect #1) |
| `app/agent/loop.py` | Hand-rolled `while finish_reason=='tool_calls'` loop: non-streamed tool-deciding calls dispatch through the registry; only the final natural-language turn streams. Owns retry-on-transient (1×), a max-iteration guard, and the integer ≤5-question gate | The judge reads this top-to-bottom; no framework, no graph compiler |
| `app/agent/state.py` | Typed Pydantic `SessionState` (messages, w2, filing_status, questions_asked, computed, pdf_bytes, trace) carried server-side in an in-memory `SESSIONS` dict — the entire persistence layer — **with TTL eviction (~30 min)** | TTL bounds memory; `pdf_bytes` (~100–300 KB) with no eviction would OOM Render's 512 MB tier (cross-backend defect #5) |
| `app/agent/tools.py` | Typed tool registry: `name → (Pydantic JSON-Schema, callable)`. Dispatch is literally validate-args → guardrail-gate → `registry[name](**args)`. Tools: `extract_w2`, `set_filing_status` (enum), `compute_1040`, `fill_1040_pdf`, `ask_user` | LLM cannot do math or PDF work inline — tools are thin wrappers over deterministic modules |
| `app/guardrails.py` | Five **code-enforced** gates, each writing a verdict to the trace: `on_task_gate`, `validate_w2`, `validate_return` (**runtime internal-consistency invariants**), `question_turn_contract`, `redact_ssn` | The ≤5-question gate is a **server-enforced turn contract** (counts `ask_user` calls; only `ask_user` may ask). The final chat **refund/owed is server-templated from `state.computed`** — the model never authors the number in prose (pre-build review) |
| `app/tax/compute.py` + `tax/constants_2025.py` | Pure deterministic 2025 Form-1040 math: wages → std deduction by status → 2025 brackets → tax → withholding → refund/owed. Constants are data, each citing its IRS source inline | The 2025 constants are verified against **independent golden cases from published IRS figures in tests** (test-time correctness). The *runtime* `validate_return` gate checks internal-consistency invariants (refund == payments − tax; taxable ≥ 0; recompute matches `state.computed`), not a golden oracle — goldens can't cover arbitrary inputs (cross-backend defect #4 / pre-build review) |
| `app/pdf/fill.py` + `pdf/field_map.py` + `assets/f1040_2025.pdf` | pypdf 6.x fills the **vendored** official 2025 1040: drop `/XFA`, set fields incl. the filing-status checkbox on-value `/1`, iterate all pages, flatten, return bytes | `field_map` covers **identity/header fields (name, address, SSN, filing-status) AND numeric lines** — a "completed" form, not bare numbers (cross-backend defect #2). Empirically verified: fill+drop-/XFA+flatten survives into page text |
| `app/w2/extract.py` + `fixtures/fake_w2.pdf` + `w2/build_fixture.py` | **Deterministic-only** pypdf AcroForm parse of the authored fixture into a validated `W2` model; SSN parsed code-side and masked before anything leaves the module | Vision extraction **dropped from v1** (privacy + overbuild); fixture also supplies taxpayer identity for the PDF |
| `app/observe.py` + `GET /trace` + UI panel | `record()` called at every decision point → structured `TraceRecord` (turn, decision, tool, redacted args, result, guardrail_verdict, latency) into `state.trace`, SSN redacted at write | Observation is a code obligation in the loop; the collapsible "Show agent trace" panel polls `/trace` so it's watched **live** |
| `static/index.html` + `static/app.js` | One light-mode, centered, airy chat column (no build step): message thread, file upload → `POST /upload`, text input, a **`fetch()` stream reader** rendering tokens + a **tool-progress/working indicator**, a cold-start "waking up" hint, and the trace panel | Deliberately un-polished (un-judged visuals). The progress indicator kills tool-turn "dead air" (cross-backend / claude fix #3) |

## Data Flow
```
Primary path (file a return):
 1. GET /              → load chat page
 2. POST /session      → mint session_id, seed SessionState, warm greeting inviting the W-2
 3. POST /upload       → w2/extract.py deterministic pypdf parse → W2 model (SSN masked, code-side);
                         validate_w2 (schema+range) gates it; TraceRecord written.  [0 questions]
 4. POST /chat (stream)→ loop.run_turn: model calls ask_user("What's your filing status?");
                         question_turn_contract checks <5, increments, the warm question STREAMS back.
                         (Tool-running turns stream a working indicator, not dead air.)
 5. user answers       → model calls set_filing_status (enum-validated)
 6. model calls        → compute_1040 → tax/compute.py deterministic 2025 math → state.computed
 7. validate_return    → RECOMPUTE + assert against INDEPENDENT golden checks BEFORE any PDF fill
                         (the no-fabrication gate)
 8. model calls        → fill_1040_pdf → pdf/fill.py maps identity + numeric lines onto vendored
                         official PDF, drop /XFA, flatten → state.pdf_bytes
 9. final STREAMED turn offers download; the refund/owed figure is SERVER-TEMPLATED from state.computed
                         (the model never authors the number, in the PDF or in chat)
10. GET /download/{sid}→ stream the filled official 2025 1040 PDF

Change-status path:  "actually I'm Head of Household" → set_filing_status → compute_1040 →
                     fill_1040_pdf; the trace shows std deduction + tax visibly recompute.
Refusal path:        off-task / tax-advice request → on_task_gate → canned refusal +
                     'decision: refuse' TraceRecord the judge sees fire live.
```
Source of truth: the in-memory `SESSIONS[session_id]` `SessionState` (ephemeral; TTL-evicted). The
W-2's deterministically-parsed values are authoritative; the LLM never holds a number. `GET /trace`
exposes the full redacted decision/tool/guardrail trail live.

## External Dependencies
| Dependency | Purpose | Constraint |
| --- | --- | --- |
| OpenRouter (Chat Completions) | The agent's single LLM — **one Claude Sonnet-class model** for chat + tool-calling | `OPENROUTER_API_KEY` server-side only (gitignored `.env` / Render secret). Tool-calling reliability varies by route — filter `supported_parameters=tools`, set `require_parameters:true`, and **smoke-test one real W-2→1040 tool flow before committing**. Pin a fallback model id |
| IRS Official 2025 Form 1040 PDF | The form the system fills | Public domain. **Vendor (commit)** `assets/f1040_2025.pdf`; never fetch at runtime. Verified TY2025 final, 229 fields, AcroForm+XFA, checkbox on-value `/1`. A unit test asserts every mapped field name still exists |
| pypdf 6.x (~6.14) | Fill + flatten the official PDF | Pure Python, **zero system binaries** (the deciding factor for Render free tier — pdftk is absent/undeployable). Placement near-perfect, not pixel-perfect — **eyeball the flattened output in Chrome + Acrobat before the demo**; reportlab overlay is the documented break-glass fallback (do not prebuild) |
| Render free tier | Hosting (public URL) | Cold start ~30–60s after idle is **accepted + documented** (UI "waking up" hint); 512 MB RAM ceiling drives the session TTL eviction. `uv sync`; Python 3.12 pinned. One-command local fallback `uv run uvicorn app.main:app --reload`; verification `uv run pytest` |
| uv / FastAPI / Uvicorn / pytest / python-dotenv | Runtime + web + tests + env loading | Python 3.12 via uv on native Linux. `uv run pytest` is the verification command. **`.env` is loaded via `load_dotenv()`** so `OPENROUTER_API_KEY` is present under both `uv run uvicorn` and `uv run pytest` — it is NOT auto-loaded otherwise (pre-build review) |

## Key Decisions
Recorded so the design explains its own reasoning (feeds the build-time `DECISIONS` note and the
"soundness of decisions" judging axis). Each was confirmed with the user and/or by cross-backend
verification.

1. **Hand-rolled loop, not a framework** — harness legibility is the highest-weighted axis; 3/3
   verifiers + 2/3 design proposals agreed. Pydantic AI is the documented fallback if build time runs short.
2. **Deterministic-only W-2 ingest; LLM vision dropped from v1** — 3-backend consensus: vision is
   non-load-bearing overbuild and sending the W-2 image risks leaking the SSN. Deterministic parse of
   our authored fixture is ~100% reliable and keeps SSN code-side. Vision = documented stretch.
3. **Single Claude Sonnet-class model** — follows from (2); best conversation + tool-calling
   reliability where it's judged. (The earlier split with Gemini-for-vision collapses once vision is cut.)
4. **Best-effort extra lines dropped from v1** — EITC is $0 for the *locked* ~$40k single-W-2 profile,
   so it would render blank/like a bug; the brief forbids changing the income. The "agent populates/
   changes lines" capability is instead shown via **filing-status recomputation**. Credits = stretch.
5. **Filing status: all four statuses recompute deduction/brackets; Single & HoH fully fill the PDF;
   MFJ/MFS are computation-focused** (spouse identity fields = stretch) — satisfies the mandate
   without spending the ≤5-question budget on spouse name/SSN (cross-backend scope flag).
6. **`fetch()` stream over POST, not `EventSource`** — cross-backend defect found by *both* Codex and
   Gemini: native `EventSource` is GET-only and cannot send the chat body. Tool-progress events ride
   the same stream to remove dead air.
7. **PDF fills identity/header fields, not just numbers; `validate_return` uses independent golden
   cases; `SESSIONS` gets TTL eviction** — the three remaining cross-backend defects, folded in.
8. **Pre-build review dispositions (cross-backend, 2026-06-24).** A 3-lens paths-only review (codex
   adversarial + scope, gemini feasibility) amended the spec: dependency edges fixed (F4→F12, F8→F6,
   F10→F9, F11→F7/F9); a model+env **preflight (F12)** added; the **`DECISIONS` note** made an F11
   criterion; PRD/NFR aligned (best-effort → stretch; W-2 upload = supplied AcroForm fixture only, image
   = stretch); `validate_return` split into a runtime invariant-gate vs test-time golden cases; the final
   chat refund/owed **server-templated**; **`python-dotenv`** added so `.env` loads. **Proceeded, not
   adopted:** keeping `compute_1040`/`fill_1040_pdf` as agent-called tools (a reviewer urged server
   side-effects — rejected, it would gut the tools pillar), with the mitigation that `fill_1040_pdf`
   always reads the latest `state.computed`. Build notes: NDJSON line-buffering in `app.js`; use public
   `pypdf.root_object`; document the bounded tax-math scope (no age-65/blind/dependent adjustments).

## Key Assumptions
- The judge values reading plain, legible Python over recognizing a framework (drives the hand-rolled
  choice; if false, Pydantic AI is the fallback).
- We author + commit the fake W-2 fixture with named AcroForm fields, making the deterministic parse
  ~100% reliable **and** supplying the taxpayer identity the "completed" PDF needs.
- The 2025 standard deduction + bracket constants are transcribed exactly from official IRS figures
  and **golden-tested against independent hand-computed cases** — the one place numbers must be
  double-checked; a transcription error silently corrupts every return.
- Guaranteed-core scope (single W-2 → std deduction → 2025 brackets → withholding → refund/owed) plus
  filing-status variation is the entire v1 surface — no best-effort credits, no schedules, no nested
  dependent PDF fields.
- Ephemeral in-memory state with TTL eviction is acceptable; losing a session on restart is fine for a
  demo, and TTL keeps memory under Render's 512 MB ceiling.
- A `fetch()` ReadableStream over POST works in target evergreen browsers (it does); `EventSource` is
  deliberately avoided.
- A single Claude Sonnet-class model reliably handles tool-calling + warm conversation — to be
  **smoke-tested on the live OpenRouter route before committing** the loop.

## Open Architecture Questions
Each becomes a `DECISION_LOG.md` entry when resolved.

- **OpenRouter model id + fallback** — pin the exact Claude model (and a documented fallback);
  confirm tool support + pricing at build time (ids drift). *Smoke-test before commit.*
- **Stream wire format** — finalize the NDJSON token + tool-progress event schema for `POST /chat`.
- **MFJ/MFS spouse-identity PDF fields** — stretch; decide if/when to collect spouse name/SSN (and
  whether to expand the budget for that path) vs. leaving those fields blank.
- **Deploy config** — `render.yaml` vs `Procfile`; the exact Render start command
  (`uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`) and local run string for the README.
- **Pre-demo visual check** — eyeball the flattened 1040 in Chrome's PDF viewer AND Acrobat (not
  verifiable headless) before the demo; reportlab overlay is the break-glass fallback.
- **Hackathon deadline** — still unknown; gates how much stretch (vision, spouse fields, best-effort
  credits) is built vs. deferred.

---

*Living document. Designed + cross-backend-verified at the architecture phase; revise as the build
teaches us what's actually true. Research backing: `research/irs-1040-pdf-fill.md`,
`research/w2-extraction.md`, `research/agent-harness-patterns.md`.*
