```text
VERDICT: FAIL
DIMENSIONS:
  - harness_observability: PASS
  - end_to_end_integrity: FAIL
  - privacy_security: FAIL
  - deployment_viability: FAIL
BLOCKING:
  - app/main.py: Technical incompatibility using browser-native EventSource over POST /chat.
  - app/pdf/fill.py: Technical contradiction using pypdf flatten=True with auto_regenerate=False, risking blank outputs.
  - app/agent/state.py: Memory leak risk from lack of TTL eviction on in-memory SESSIONS dictionary containing PDF bytes.
  - app/w2/extract.py: Image-based W-2 vision cross-check violates privacy NFR unless complex masking is implemented.
RIGOR: tuned
```

## Findings

### Response to Prior Claude Verifier's 5 Fixes

| Prior Claude Flagged Fix | Verdict | Verification Reason |
| :--- | :--- | :--- |
| **1. EITC phase-out on $40k profile** | **AGREE** | Since a single $40k earner with no children qualifies for $0 EITC, this marquee "best-effort additional lines" feature will appear non-functional to the judge unless the fixture's income is lowered to ~$15k. |
| **2. Vision cross-check overbuild** | **AGREE** | Setting up Gemini vision, image rendering, and parallel schema cross-checks creates high integration overhead for a non-authoritative path that can be easily deferred. |
| **3. Streaming NFR vs. Performance targets** | **AGREE** | Non-streamed tool turns will cause several seconds of UI "dead air" during computation, violating the 1-2s responsiveness target unless a tool-running indicator is emitted. |
| **4. SSN privacy stance vs. vision path** | **AGREE** | Uploading W-2 images to OpenRouter leaks the SSN in raw pixel form, requiring complex image-redaction steps that are prone to failure and require heavy system dependencies. |
| **5. Unverified OpenRouter features** | **AGREE** | Structured output models and image inputs on OpenRouter have undocumented edge cases and high latency, requiring early integration smoke tests. |

---

### Analysis of the 3 Architecture Forks

1. **Agent harness: hand-rolled loop vs. Pydantic AI framework**
   - **Verdict:** **AGREE** with the recommendation (Hand-rolled loop).
   - **Reasoning:** Hand-rolling the loop provides full transparency to the judge (the highest-weighted rubric item) and eliminates external framework complexity and streaming-crash bugs.
2. **W-2 Ingestion: deterministic-default (vision as cross-check) vs. vision-primary**
   - **Verdict:** **DISAGREE** with the recommendation (Hybrid path).
   - **Reasoning:** To satisfy the privacy NFR without the high complexity of image-based SSN masking, the vision cross-check should be dropped entirely for v1, making the deterministic AcroForm parse the sole path.
3. **OpenRouter model for the agent loop**
   - **Verdict:** **AGREE** with the recommendation (Claude Sonnet-class for the loop).
   - **Reasoning:** A Sonnet-class model is highly reliable for tool selection and state transitions, though Gemini 2.5 Flash should be dropped if the vision cross-check is removed.

---

### New Architecture Issues Missed by Claude

#### 1. SSE over POST Protocol Incompatibility
The architecture specifies that [app/main.py](file:///home/brent-gibson/projects/taxathon/app/main.py)'s `POST /chat` route returns an SSE token stream for the final assistant message, and that the frontend uses a standard `EventSource` consumer to render the streamed tokens. However, the browser's native `EventSource` API **only** supports `GET` requests and cannot transmit a `POST` request payload containing the user's input.
- **Impact:** The frontend will fail to connect or stream tokens using native Javascript.
- **Remediation:** Either the frontend must use a standard `fetch` call and process the response body stream manually as a stream of line-delimited JSON/tokens, or the chat loop must be split into a `POST /chat` submission and a separate `GET /stream?session_id=X` SSE stream connection.

#### 2. pypdf Flattening & Appearance Stream Deletion
The architecture states that [app/pdf/fill.py](file:///home/brent-gibson/projects/taxathon/app/pdf/fill.py) will set `auto_regenerate=False` and `flatten=True` when updating field values. In `pypdf`, if form fields are flattened without auto-regenerating appearance streams, the library simply strips the interactive form fields *without* writing their text representations into the static page content stream.
- **Impact:** The downloaded Form 1040 PDF will render as completely blank or missing all filled-out tax figures when opened in standard PDF readers.
- **Remediation:** Set `auto_regenerate=True` and adjust text field spacing, or use a library overlay (like `reportlab`) as a robust fallback.

#### 3. Ephemeral SESSIONS RAM Memory Leak
The app stores session states (including raw `pdf_bytes` which are ~100–300KB each) inside a global, in-memory `SESSIONS` dictionary cache with no eviction policies.
- **Impact:** On Render's free tier (which has a strict 512MB RAM ceiling), multiple test runs or automated judging scans will cause a slow memory leak, eventually triggering an Out-of-Memory (OOM) container crash.
- **Remediation:** Implement a lightweight cleanup task (e.g., using FastAPI's background tasks or middleware) to evict sessions older than 30 minutes.

#### 4. MFJ Spouse Name/SSN Questionnaire Limit
Filing Status variation (MFJ / MFS) requires collecting spouse name, spouse SSN, and filing-status details. If a user selects Married Filing Jointly, asking for these items individually will immediately exceed the strict "≤5 questions" budget gate.
- **Impact:** The agent will either fail to populate mandatory spouse fields on the PDF (causing a corrupted return) or violate the ≤5-question constraint.
- **Remediation:** Restrict MFJ to a stretch goal, allow a higher question budget (e.g., ≤8 questions) specifically when MFJ/MFS is active, or allow batch inputs (e.g. asking for spouse name and SSN in a single prompt).

---

## Open Questions

1. **How should the streaming protocol be implemented on the frontend?**
   Should we drop SSE in favor of a standard `fetch` stream reader (NDJSON) to keep `POST /chat` simple and avoid multi-endpoint coordination?
2. **What is the exact scope of MFJ in v1?**
   If MFJ is supported, does the budget gate expand, or will we accept blank spouse fields on the official Form 1040?
3. **How will we handle clean standard deduction variations on the PDF?**
   Does the official Form 1040's filing status checkbox group act as a radio group (with index options `1`-`5`) rather than individual checkboxes?

---

## Verification Evidence

- [PRD.md §5](file:///home/brent-gibson/projects/taxathon/PRD.md#L49-L65) sets the guaranteed core scope and filing status variation, while [PRD.md §8](file:///home/brent-gibson/projects/taxathon/PRD.md#L97-L107) enforces Python 3.12, FastAPI, and OpenRouter constraints.
- [NFR_UX.md Performance](file:///home/brent-gibson/projects/taxathon/NFR_UX.md#L15-L25) defines response times (1-2s first token), which conflict with the non-streamed tool turns in the recommended architecture.
- [NFR_UX.md Security](file:///home/brent-gibson/projects/taxathon/NFR_UX.md#L26-L38) forbids sending raw SSNs to LLM prompts, which is violated by the raw W-2 image uploads in the proposed vision path.

---

## Residual Risk

- **Render Cold Starts:** The 30-60s spin-up time on Render's free tier remains a risk for judge drop-offs; a clear "Waking up..." visual indicator is necessary on load.
- **OpenRouter Rate Limits:** Low-tier OpenRouter keys may encounter rate limits or connection failures; the agent must implement robust retries and fallback models.

---

## Gate Verdict

**Overall Verdict:** `has_gaps`

### Bottom Line
The "Deterministic Spine, Agentic Skin" architecture is structurally sound and represents the correct approach for securing a correct tax return, but it suffers from severe implementation gaps. The single most important change is to **drop the vision cross-check entirely** to satisfy the SSN-privacy NFR, simplify Render dependencies, and refocus engineering resources on resolving the SSE-over-POST transport incompatibility and `pypdf` flattening bugs.

---

## Questions

1. Would you prefer dropping the vision cross-check entirely for the v1 release, focusing solely on the deterministic PDF AcroForm parse to guarantee privacy and deployment stability?
2. Shall we use a custom `fetch`-based stream reader on the frontend instead of browser-native `EventSource` to resolve the `POST` stream compatibility problem?
