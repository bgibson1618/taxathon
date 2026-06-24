Mostly coherent and intentionally narrow, but the ledger has a few scope/dependency gaps that could let required work fall out of the build loop.

## FINDINGS

1. **Best-effort 1040 lines are still in the PRD but out of the feature ledger.**

   **CITATION** — `/home/brent-gibson/projects/taxathon/PRD.md:58-59`:
   > “- **Best-effort extension:** additional standard 1040 lines/credits the inputs clearly support
   >   (e.g. EITC for a qualifying low-income filer) — populated only when computable correctly.”

   `/home/brent-gibson/projects/taxathon/FEATURES.md:11-13`:
   > “Grounded in `ARCHITECTURE.md` ("Deterministic Spine, Agentic Skin"). **v1 scope only** — stretch
   > items (LLM-vision W-2 cross-check, MFJ/MFS spouse-identity PDF fields, best-effort credit lines) are
   > deliberately out of this ledger per the architecture's Key Decisions.”

   **ANCHOR** — firm

   **WHY IT MATTERS** — A builder or reviewer reading the PRD will expect additional computable lines/credits in v1, while the build ledger will never produce them. That creates avoidable done-definition drift.

   **DISPOSITION SUGGESTION** — amend the PRD to move best-effort lines/credits to stretch, or add a feature that explicitly delivers the narrowed best-effort boundary.

2. **The required `DECISIONS` note has no feature coverage.**

   **CITATION** — `/home/brent-gibson/projects/taxathon/PRD.md:63-65`:
   > “- Deliverables: **source repo**, the live URL, a **realistic fake W-2 fixture**, and a short
   >   **`DECISIONS` note** (~half a page) covering the open-item choices.”

   `/home/brent-gibson/projects/taxathon/FEATURES.md:173-178`:
   > “- The app is deployed to a public URL (Render or comparable) that loads the chat and serves the end-to-end
   >   flow; a "waking up" hint covers cold start.
   > - A documented one-command local run (`uv run uvicorn app.main:app ...`) starts the app and serves the same
   >   flow.
   > - The repo contains the source, the fake W-2 fixture, and the vendored official 2025 1040 PDF.”

   **ANCHOR** — certain

   **WHY IT MATTERS** — The brief judges “soundness of decisions”; without ledger coverage, the build can finish source/deploy artifacts while omitting the explicit decision artifact.

   **DISPOSITION SUGGESTION** — amend F11 to require the `DECISIONS` note, or add a small final documentation feature depending on the architecture decisions.

3. **Final deployment does not depend on all v1 user-facing requirements.**

   **CITATION** — `/home/brent-gibson/projects/taxathon/FEATURES.md:110-122`:
   > “## F7 — Filing-status variation”
   > “- **Depends on:** F1, F3, F4”
   > “- Single and HoH produce a fully-filled PDF; MFJ/MFS produce correct computed figures (spouse-identity
   >   PDF fields are out of v1 scope).”

   `/home/brent-gibson/projects/taxathon/FEATURES.md:138-149`:
   > “## F9 — Warm, human conversation”
   > “- **Depends on:** F4, F5, F8”
   > “- Error and recovery messages read as calm and guiding, not blunt.”

   `/home/brent-gibson/projects/taxathon/FEATURES.md:166-168`:
   > “## F11 — Public deployment + local fallback”
   > “- **Depends on:** F10”

   **ANCHOR** — firm

   **WHY IT MATTERS** — F7 and F9 are explicit v1/judge-facing requirements, but F11 can be scheduled after F10 without waiting for either. A dependency-driven build could deploy before filing-status variation and conversation sign-off are actually complete.

   **DISPOSITION SUGGESTION** — amend F11 to depend on F7, F9, and F10, or add a final readiness feature that depends on every required user-facing feature.

4. **Trace panel ownership is duplicated across F6 and F8 without a dependency.**

   **CITATION** — `/home/brent-gibson/projects/taxathon/FEATURES.md:96-105`:
   > “## F6 — Live observation trace”
   > “**Functionality:** A judge can watch what the agent did and why, live, while it runs — every decision,
   > tool call, and guardrail verdict is recorded and viewable at `/trace` and in a collapsible UI panel.”

   `/home/brent-gibson/projects/taxathon/FEATURES.md:124-136`:
   > “## F8 — Streaming chat UI + minimal web page”
   > “- **Depends on:** F4”
   > “- The page supports W-2 file upload, message send, a cold-start "waking up" hint, and the collapsible
   >   trace panel.”

   **ANCHOR** — firm

   **WHY IT MATTERS** — F8 can be built in parallel with F6 while still claiming the trace panel. That invites duplicated UI work, a stubbed panel, or unclear proof ownership for the judge-visible observation surface.

   **DISPOSITION SUGGESTION** — amend F8 to remove the trace panel and leave it wholly in F6, or make F8 depend on F6 if the UI panel is part of the chat page delivery.

5. **Accessibility basics from NFR are not carried into the UI feature.**

   **CITATION** — `/home/brent-gibson/projects/taxathon/NFR_UX.md:61-64`:
   > “### Accessibility *(human-facing UI — minimal, right-sized to the un-judged visual bar)*
   > - **Standard / target:** Reasonable defaults (not a full WCAG audit, given the minimal-UI mandate).
   > - **Specifics:** Keyboard-usable chat (type + Enter to submit); readable contrast; legible default
   >   font size; **reduced-motion respected** (the only motion is a typing indicator). i18n: English only.”

   `/home/brent-gibson/projects/taxathon/FEATURES.md:132-136`:
   > “- The final assistant turn streams progressively in the browser via a `fetch()` stream (not `EventSource`).
   > - Tool-running turns show a working/typing indicator, so the user sees it is working rather than dead air.
   > - The page supports W-2 file upload, message send, a cold-start "waking up" hint, and the collapsible
   >   trace panel.”

   **ANCHOR** — firm

   **WHY IT MATTERS** — The UI can satisfy F8 while missing the NFR’s low-cost accessibility contract, especially keyboard behavior and reduced-motion handling.

   **DISPOSITION SUGGESTION** — amend F8 success criteria with a lightweight accessibility check: keyboard send/upload/download path, readable contrast/default font size, and reduced-motion behavior for the typing indicator.

## NOTES

No uncited scope-growth concern stood out. The ledger’s exclusions for LLM vision, MFJ/MFS spouse identity fields, and best-effort credits are explicit architecture choices; the main issue is making upstream docs and dependency gates match those choices.

## Questions

None.