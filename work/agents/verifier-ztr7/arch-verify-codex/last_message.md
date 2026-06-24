VERDICT: FAIL
DIMENSIONS:
  - requirements fit: FAIL
  - harness quality: PASS
  - end-to-end feasibility: FAIL
  - conversation/UX: FAIL
  - scope discipline: FAIL
BLOCKING:
  - Architecture / PDF fill: numeric-only 1040 mapping risks producing an incomplete official form, despite the PRD requiring a completed downloadable 1040.
  - Architecture / streaming API: `POST /chat` plus a browser `EventSource` consumer is incompatible without a different streaming transport.
  - Architecture / question gate: the `ask_user` tool gate does not stop the model from asking extra or multi-part questions in final streamed prose.
RIGOR: tuned

## Findings

**verdict:** has_gaps

The deterministic spine is the right architectural center, but the current recommendation still has build-blocking gaps against the highest-weighted outcomes: harness readability, real end-to-end output, and ≤5 warm questions. The gaps are fixable, but they should be resolved before implementation.

**on Claude's 5 fixes**

- AGREE — EITC as the only best-effort line is underfunded for the stated ~$40k profile; PRD requires best-effort lines only when correctly computable, but the demo may visibly show nothing. See `PRD.md:41-43`, `PRD.md:58-59`.
- AGREE — the vision cross-check is not load-bearing and conflicts with the keep-it-simple / no-scope-creep constraint. See `PRD.md:72`.
- AGREE — final-turn-only streaming leaves tool-heavy turns with dead air; NFR explicitly calls for streaming or progress while tools work. See `NFR_UX.md:16-24`, `NFR_UX.md:81-83`.
- AGREE — SSN image masking is a hard privacy dependency if vision remains; raw SSNs should stay out of prompts/logs/traces. See `NFR_UX.md:31-38`.
- AGREE — OpenRouter tool and image/schema behavior must be live-smoked; end-to-end operation is a top criterion, not an assumption. See `PRD.md:88-95`.

**on the 3 forks**

- Hand-rolled loop: agree. Harness quality is highest-weighted, and plain code is easier for judges to inspect than a framework layer. Caveat: the output/question gates must be server-enforced, not just tool-enforced.
- Deterministic W-2 primary + vision cross-check: partially agree. Deterministic primary is correct; vision should be stretch, not v1 critical path.
- Split Claude-for-loop + Gemini-for-vision: disagree as the default v1 path. Use one verified tool-capable chat model first; add Gemini only if the optional vision stretch survives the privacy and schedule gates.

**NEW issues Claude missed**

- The PDF fill plan appears incomplete. The described `field_map.py` covers numeric lines plus filing-status checkbox, but a “completed” official 1040 needs taxpayer identity/header fields at minimum: name, address, SSN, and spouse fields when relevant. PRD requires a completed downloadable official PDF, not just computed numbers on a form. See `PRD.md:17-18`, `PRD.md:61`, `PRD.md:88-89`.
- Filing-status support is overclaimed. PRD requires Single/MFJ/MFS/HoH variation, but the architecture only asks for filing status and uses one W-2. MFJ/MFS/HoH can require spouse/dependent/qualifying-person facts and PDF fields; either constrain v1 to demonstrable computation variation or add the minimum data contract. See `PRD.md:39-40`, `PRD.md:60`, `PRD.md:93`.
- Native `EventSource` cannot send a `POST /chat` body. The architecture says `POST /chat` returns SSE and `static/app.js` uses EventSource; that will not work in a standard browser without a polyfill or a two-step stream design. Use `fetch()` streaming for POST, or POST to create a run and GET an SSE stream.
- The ≤5-question gate has an enforcement loophole. Counting `ask_user()` calls does not prevent the LLM from asking two questions in one final message, or asking a question without the tool. The server needs a turn-type contract: only server-rendered `ask_user` output may contain user-facing questions, and final streamed prose must be checked or constrained. See `PRD.md:54`, `PRD.md:92`, `NFR_UX.md:84-85`.
- `validate_return()` may be tautological if it recomputes with the same constants/function path as `compute_return()`. It proves internal consistency, not correctness of 2025 tax constants. Add independent golden cases or table-level tests from source figures. See `PRD.md:55-57`, `PRD.md:90-91`.

## Open Questions

- Is the v1 artifact expected to look like a actually completed 1040 header, or is a numeric-line demo acceptable? The PRD reads as completed form.
- Are all filing statuses required in the running demo, or only enough variation to prove deduction/bracket recomputation?

## Verification Evidence

Reviewed `PRD.md`, `NFR_UX.md`, and `INTAKE.md` against the supplied recommended architecture. This was architecture verification only; no implementation or tests exist in the reviewed surface.

## Residual Risk

Even after these fixes, the riskiest proof points remain PDF field behavior on the vendored 1040, exact 2025 constant transcription, OpenRouter tool-call reliability, and Render cold-start/live-demo reliability.

## Gate Verdict

FAIL / has_gaps. Build the deterministic spine, but first narrow v1 to deterministic W-2 ingest, complete 1040 identity+numeric PDF fill, a browser-valid streaming plan, and a server-enforced question contract. The single most important change is to make “completed official 1040” literal, including identity/header fields and status-dependent required fields, because that is what the judge will open and inspect.

## Questions

None.