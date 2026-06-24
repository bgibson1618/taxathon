# Implementation - Taxathon

> **Generated snapshot** (D21 / F30) — rendered by `scripts/render-snapshot.mjs` from
> `FEATURES.md` + `.kodos/state.json`. **Do not hand-edit** — re-render instead.
> Rendered: 2026-06-24T21:14:06Z.

## Status

**Phase `done` — 12 of 12 features proved.**

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
| F4 | Agent chat loop + tool dispatch + state | observed | proved | smoke_e2e (final tree): loop dispatched extract_w2->set_filing_status->compute_1040->fill_1040_pdf, state car… |
| F5 | Guardrails: enforced + visible | test + observed | proved | install_guardrails() wired into app startup; live smoke_trace shows the ≤5 budget refusal firing on the real… |
| F6 | Live observation trace | observed + test | proved | live https://taxathon.onrender.com/trace populated; local trace smoke records tool/talk/refuse, SSN redacted |
| F7 | Filing-status variation | test + observed | proved | smoke_filing_status (final tree): single->HoH recompute std 15000->22500, tax 2762->1760, refund 238->1240 on… |
| F8 | Streaming chat UI + minimal web page | observed | proved | live URL: chat page served + POST /chat/stream NDJSON streaming on the deployed route |
| F9 | Warm, human conversation | sign-off | proved | self-judged (user waived user sign-off under time pressure): live tone warm + plain + human (greeting + 'Grea… |
| F10 | End-to-end filing flow | observed | proved | smoke_e2e (final tree): 771KB filled official 2025 1040 (taxpayer name + refund $238) produced and downloadab… |
| F11 | Public deployment + local fallback | observed | proved | https://taxathon.onrender.com/ LIVE: GET /health ok, GET / serves the chat page, POST /chat/stream streams a… |
| F12 | Model + environment preflight | test + observed | proved | live model anthropic/claude-sonnet-4.6 served tool-calls on the deployed Render server |
