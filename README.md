# Taxathon — Agentic Tax-Filing Assistant

Chat your single W-2 into a completed **2025 IRS Form 1040** — a warm, ≤5-question conversation in,
a downloadable filled official 1040 out.

**🔗 Live demo:** https://taxathon.onrender.com/
**▶️ One-command local run:** `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` → http://localhost:8000

> Hackathon prototype. Fake data only — **not tax advice**, no real PII, no e-filing.

## What it does

Upload the supplied fake W-2, have a short friendly chat, and download a completed, **official** 2025
Form 1040. A judge can watch the agent's every decision live at `/trace`. Verified end-to-end: a
single-W-2 ($40k) filer gets a correct **$238 refund** on a real filled PDF.

## The harness — four pillars, *enforced and visible* (not cosmetic)

The interesting part is the architecture (a hand-rolled "Deterministic Spine, Agentic Skin"): the LLM
only phrases conversation and picks tools; **every correctness/output step is deterministic Python**.

| Pillar | Where it lives | How it's enforced + visible |
| --- | --- | --- |
| **Chat loop** | `app/agent/loop.py` | A plain `while finish_reason=='tool_calls'` loop over OpenRouter; typed `SessionState` carries context across turns (`app/agent/state.py`). |
| **Tools** | `app/agent/tools.py` | Typed registry; dispatch is `validate-args → guardrail-gate → run`. Real work: `extract_w2`, `set_filing_status`, `compute_1040`, `fill_1040_pdf`. The LLM never authors a number. |
| **Guardrails** | `app/guardrails.py` | Five **code** gates: on-task refusal, ≤5-question turn contract, `validate_return` (no-fabrication recompute *before* any PDF fill), SSN redaction, server-templated refund/owed. |
| **Observation** | `app/observe.py` + `GET /trace` | Every decision/tool/refusal → a redacted `TraceRecord`, watchable live in the UI's "Show agent trace" panel. |

Deterministic core: `app/tax/compute.py` (+ `constants_2025.py`, cited to Rev. Proc. 2024-40) does the
2025 1040 math; `app/pdf/fill.py` fills the **vendored official** `assets/f1040_2025.pdf` with pypdf
(drops `/XFA`, flattens); `app/w2/extract.py` parses the W-2 with SSN kept code-side.

## Run & verify

```bash
uv sync                                  # install (Python 3.12)
echo "OPENROUTER_API_KEY=sk-or-..." > .env
uv run pytest                            # 159 tests, the verification command
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Deploy (Render)

`render.yaml` is a Blueprint: New → **Blueprint** → select the repo → set `OPENROUTER_API_KEY` as a
secret. Build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## Scope (v1)

Single W-2, all four filing statuses recompute (Single/HoH fully fill the PDF; MFJ/MFS computation-focused).
Out: image/OCR W-2 upload, spouse-identity fields, extra credit lines (EITC is $0 at the fixed $40k profile).
See **`DECISIONS.md`** for the open-item choices and **`DECISION_LOG.md`** for the full record.

## Project docs

Built with [KodOS](https://github.com/). `PRD.md` · `ARCHITECTURE.md` · `FEATURES.md` (the ledger,
12/12 proved) · `IMPLEMENTATION.md` (generated status) · `BUILD_LOG.md` (build journal) · `research/`.
