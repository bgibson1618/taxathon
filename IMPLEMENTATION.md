# Implementation - Taxathon

> **Generated snapshot** (D21 / F30) — rendered by `scripts/render-snapshot.mjs` from
> `FEATURES.md` + `.kodos/state.json`. **Do not hand-edit** — re-render instead.
> Rendered: 2026-06-24T21:06:19Z.

## Status

**Phase `build` — 11 of 12 features proved.** Needs-you: F11 (reasons in the table).

Current status and the next action are **owned by `.kodos/state.json`** — read them live
(this snapshot never asserts them, D2):

```bash
node scripts/schedule.mjs FEATURES.md .kodos/state.json   # or: /kodos:go
```

History lives in `BUILD_LOG.md` (append-only journal) and `DECISION_LOG.md` (durable
decisions); verify live with the project's verification command rather than trusting any
rendered count.

## Features (rendered from state)

| id | title | proof | status | evidence (abridged) |
|---|---|---|---|---|
| F1 | 2025 tax computation engine | test | proved | uv run pytest tests/test_tax.py: 18 passed (full suite 39 passed); independent bracket-walk cross-check match… |
| F2 | W-2 ingest (deterministic parse) | test | proved | uv run pytest tests/test_w2.py: 15 passed; fixture parses to expected; masked_ssn ***-**-6789; range validati… |
| F3 | Filled official 2025 1040 PDF + download | test + sign-off | proved | parent rendered fixtures/sample_filled_1040.pdf p1 -> PNG, eyeballed: genuine official 2025 1040, populated (… |
| F4 | Agent chat loop + tool dispatch + state | observed | proved | uv run python scripts/smoke_agent.py: live model dispatched extract_w2/ask_user/set_filing_status/compute_104… |
| F5 | Guardrails: enforced + visible | test + observed | proved | install_guardrails() wired into app startup; live smoke_trace shows the ≤5 budget refusal firing on the real… |
| F6 | Live observation trace | observed + test | proved | uv run python scripts/smoke_trace.py: exit 0, 7 turn-by-turn records over GET /trace (extract_w2->ask_user[qu… |
| F7 | Filing-status variation | test + observed | proved | scripts/smoke_filing_status.py live: a real conversation changes status and the std deduction/tax/refund visi… |
| F8 | Streaming chat UI + minimal web page | observed | proved | live uvicorn: GET / serves the chat page; POST /chat/stream returns NDJSON token+done events (warm reply stre… |
| F9 | Warm, human conversation | sign-off | proved | self-judged (user waived user sign-off under time pressure): live tone warm + plain + human (greeting + 'Grea… |
| F10 | End-to-end filing flow | observed | proved | scripts/smoke_e2e.py: ONE turn dispatched extract_w2->set_filing_status->compute_1040->fill_1040_pdf; state.p… |
| F11 | Public deployment + local fallback | observed | needs-you | needs-you: Public-URL deploy is the user outward action (Render account + push to public GitHub; self-hosted… |
| F12 | Model + environment preflight | test + observed | proved | uv run python scripts/smoke_tools.py: exit 0; live tool_call from anthropic/claude-sonnet-4.6 |
