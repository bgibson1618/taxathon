# Decision Log — Taxathon

Why things are the way they are. The durable record behind `ARCHITECTURE.md` / `FEATURES.md`, and the
seed for the build-time **`DECISIONS` note** the brief requires (F11). Newest decisions on top.

---

### D11 — Pre-build cross-backend review amended the plan (2026-06-24)
A 3-lens paths-only review (codex: adversarial + scope; gemini/antigravity: feasibility) read the
discovery artifacts cold and found ~12 citeable issues. All applied as spec/doc edits **before** build:
fixed dependency edges (F4→F12, F8→F6, F10→F9, F11→F7/F9); added a model+env **preflight (F12)**; made
the `DECISIONS` note an F11 criterion; aligned PRD/NFR (best-effort → stretch; W-2 upload = supplied
AcroForm fixture only); split `validate_return` into a runtime invariant-gate vs test-time golden cases;
**server-templated** the chat refund/owed; added `python-dotenv`. **Rejected** one finding (move
compute/fill to server side-effects) — it would gut the tools pillar; mitigated instead (fill reads
latest `state.computed`).

### D10 — Model + env preflight (F12) before the agent loop (2026-06-24)
"Does it actually work" is the #2 judged axis and rests on OpenRouter tool-calling, an unverified
external. A small preflight pins the model + a fallback, loads `.env` (via `python-dotenv`), and smoke-
tests one real tool-call **before** F4 is built on it.

### D9 — No-fabrication: runtime invariants + server-templated number + test goldens (2026-06-24)
The "no-fabrication" guarantee has three legs: (a) test-time golden cases prove the 2025 math vs published
IRS figures; (b) a runtime `validate_return` gate asserts internal-consistency invariants before any PDF
fill; (c) the refund/owed shown in chat is templated from `state.computed`, so the model can't misstate a
number in prose. (Golden cases can't be a runtime oracle for arbitrary inputs.)

### D8 — Streaming via `fetch()` stream over POST, not `EventSource` (2026-06-24)
Two backends independently caught that browser-native `EventSource` is GET-only and can't carry the chat
body. v1 streams NDJSON over `POST /chat` read with a `fetch()` ReadableStream (line-buffered); tool-
progress events ride the same stream to remove dead air.

### D7 — Filing status: all four recompute; Single/HoH fully fill, MFJ/MFS compute-only (2026-06-24)
Satisfies the brief's filing-status mandate via correct recomputation without spending the ≤5-question
budget on spouse identity. MFJ/MFS spouse-identity PDF fields are a stretch goal.

### D6 — Best-effort extra lines dropped from v1 (2026-06-24)
EITC (the only candidate) is $0 for the *locked* ~$40k single-W-2 profile, so it would render blank/like a
bug, and the brief forbids changing the income. The "agent changes lines" capability is shown instead via
filing-status recomputation. Extra credit lines = stretch.

### D5 — Deterministic-only W-2 ingest; LLM vision dropped from v1 (2026-06-24)
3-backend consensus: vision is non-load-bearing overbuild and sending the W-2 image risks leaking the SSN.
A deterministic pypdf AcroForm parse of our authored fixture is ~100% reliable and keeps the SSN code-side.
Vision/OCR of arbitrary W-2s = documented stretch.

### D4 — Single Claude Sonnet-class model via OpenRouter (2026-06-24)
Follows from dropping vision; best conversation + tool-calling reliability where it is judged. (`.env`
already carries `OPENROUTER_API_KEY`.)

### D3 — Hand-rolled agent loop, not a framework (2026-06-24)
Harness legibility is the highest-weighted judging axis; a hand-rolled loop is the most legible answer and
avoids a known streaming-validator crash class. Pydantic AI is the documented fallback if time runs short.

### D2 — Official 2025 1040 filled with pypdf (vendored, drop `/XFA`, flatten) (2026-06-24)
Empirically verified end-to-end on the real, final TY2025 form (229 fields; values survive flatten into
page text). Pure-Python (no system binaries) is the deciding factor for Render free tier. `field_map`
covers identity/header + numeric lines; reportlab overlay is the break-glass fallback.

### D1 — Architecture = "Deterministic Spine, Agentic Skin" (2026-06-24)
A hand-rolled FastAPI agent loop over OpenRouter where every correctness/output step (W-2 read, tax math,
PDF fill, question gate, refusals) is deterministic Python and the LLM only phrases conversation and picks
tools. Chosen from a 3-angle design panel + synthesis, then verified across Claude + Codex + Gemini.
Directly optimizes the highest-weighted axis (a judge reads the code and sees each pillar enforced, not
cosmetic).
