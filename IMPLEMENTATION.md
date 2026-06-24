# Implementation - Taxathon

> **Generated snapshot** (D21 / F30) — rendered by `scripts/render-snapshot.mjs` from
> `FEATURES.md` + `.kodos/state.json`. **Do not hand-edit** — re-render instead.
> Rendered: 2026-06-24T20:28:25Z.

## Status

**Phase `build` — 3 of 12 features proved.**

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
| F3 | Filled official 2025 1040 PDF + download | test + sign-off | todo | — |
| F4 | Agent chat loop + tool dispatch + state | observed | todo | — |
| F5 | Guardrails: enforced + visible | test + observed | todo | — |
| F6 | Live observation trace | observed + test | todo | — |
| F7 | Filing-status variation | test + observed | todo | — |
| F8 | Streaming chat UI + minimal web page | observed | todo | — |
| F9 | Warm, human conversation | sign-off | todo | — |
| F10 | End-to-end filing flow | observed | todo | — |
| F11 | Public deployment + local fallback | observed | todo | — |
| F12 | Model + environment preflight | test + observed | proved | uv run python scripts/smoke_tools.py: exit 0; live tool_call from anthropic/claude-sonnet-4.6 |
