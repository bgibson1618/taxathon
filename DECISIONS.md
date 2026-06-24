# DECISIONS — Taxathon (half-page)

The brief left several things open ("anything") and judges the *soundness* of the calls. Here are the
key ones; the full dated record is in `DECISION_LOG.md`.

- **Hand-rolled agent loop, not a framework.** Harness legibility is the highest-weighted axis — a plain
  `while tool_calls` loop is the most legible answer a judge can read top-to-bottom. (Pydantic AI was the
  documented fallback.)
- **Deterministic spine.** The LLM only talks and picks tools; W-2 parse, 2025 tax math, PDF fill, the
  ≤5-question gate, and refusals are all deterministic Python. The model never owns a number.
- **No-fabrication, three ways.** Tax math is golden-tested against published 2025 IRS figures; a runtime
  `validate_return` gate asserts internal consistency *before* any PDF fill; the refund/owed shown in chat
  is server-templated from the computed state. The model can't misstate a figure in the form or in prose.
- **Official 1040 via pypdf.** Fill the *vendored* official 2025 form (drop `/XFA`, flatten) — empirically
  verified to survive into the PDF. Pure-Python (no system binaries) was the deciding factor for Render free tier.
- **Deterministic-only W-2 ingest; LLM vision dropped from v1.** Vision was non-load-bearing overbuild and
  risked leaking the SSN to the model; a deterministic AcroForm parse of our authored fixture is ~100% reliable.
- **Best-effort credit lines dropped.** EITC is $0 for the *fixed* $40k single profile (the brief locks the
  income), so it would render blank; the "agent changes lines" capability is shown via filing-status recompute instead.
- **Single Claude model via OpenRouter** (`anthropic/claude-sonnet-4.6`, fallback `4.5`), pinned after a live
  tool-calling smoke test so "does it work" doesn't rest on an unverified assumption.
- **Streaming via `fetch()` over POST (not `EventSource`).** EventSource is GET-only and can't carry the chat
  body — caught by cross-backend pre-build review before any code was written.
- **Ephemeral in-memory state with TTL eviction.** No datastore (state is throwaway for a demo); TTL bounds
  memory under Render's 512 MB tier.

**Process:** designed via a 3-angle design panel + synthesis, then adversarially verified across three model
families (Claude + Codex + Gemini) twice — at architecture and at a pre-build review — which caught real
defects (the EventSource bug, missing PDF identity fields, the runtime-vs-test validation split) as cheap
spec edits before the build.
