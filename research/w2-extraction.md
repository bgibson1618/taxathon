# Research: Reading a user-uploaded W-2 into structured fields for an agent tool

> Taxathon architecture-phase research. Scope: how the agent reads the supplied **fake** W-2
> (PDF/image upload) into the structured fields the code-side 1040 computation needs
> (Box 1 wages, Box 2 federal withholding, filing-status hints, etc.).
> Author: Researcher role. Date: 2026-06-24.

---

## Question

How should the agent ingest a user-uploaded W-2 into structured fields for a tool call?
Compare (a) LLM vision extraction via OpenRouter, (b) OCR (tesseract) + parsing,
(c) authoring our own machine-readable W-2 (AcroForm / clean text layer) we parse
deterministically, and (d) a hybrid (vision with a deterministic fallback). Weigh
reliability vs. "agentic impressiveness," the "must actually work end-to-end" bar, the
≤5-question budget, and the privacy constraint (keep raw SSN out of LLM prompts where feasible).

## Short Answer

**Recommend (d), a hybrid, with the deterministic path as the default and the LLM-vision path
as the visible "agentic" tool — and we author the fixture so both paths are easy.**

Concretely: **author the fake W-2 as a PDF with an embedded AcroForm (named fillable fields) AND
a clean text layer.** The W-2 ingestion tool first tries **deterministic extraction** (read the
AcroForm field values with `pypdf`, or fall back to parsing the text layer). Because we control the
fixture, this is ~100% reliable and instant, satisfies "must actually work end-to-end," and lets us
**never put the raw SSN into an LLM prompt** (the tool can drop/redact SSN before anything is logged
or sent upstream). For the harness's "tools" and "agentic" pillars, **also wire an OpenRouter
vision-extraction tool** (Gemini 2.5 Flash or similar) that the agent can call — either as the
primary extractor on arbitrary/scanned W-2s (impressive, judge-visible) with the deterministic parse
as a cross-check/fallback, or as the explicit fallback when the deterministic parse fails. Either
ordering is defensible; the key is that **a deterministic parse of a fixture we author is what
guarantees the demo works**, and **code-side validation gates every extracted number before it
reaches the tax math** (NFR: "validate the computed return before filling the PDF").

This keeps the guaranteed-core numbers trustworthy (no fabricated wages/withholding), preserves the
privacy stance (raw SSN stays code-side), and still demonstrates a real, observable vision tool.

---

## Sources

OpenRouter (primary / vendor docs):
- Structured Outputs — https://openrouter.ai/docs/guides/features/structured-outputs
- Multimodal overview (images + PDFs) — https://openrouter.ai/docs/guides/overview/multimodal/overview
- PDF inputs / file-parser plugin & engines — https://openrouter.ai/docs/guides/overview/multimodal/pdfs
- Universal PDF Support announcement — https://openrouter.ai/announcements/universal-pdf-support
- Vision-models collection — https://openrouter.ai/collections/vision-models
- Models list — https://openrouter.ai/models

OpenRouter PDF-parsing "docs vs. reality" disagreement (see Risks):
- Mick.net on X (Mar 26 2026): OpenRouter /chat/completions PDF behavior reportedly not matching the
  PDF docs claim — https://x.com/mick__net/status/2037131555160649976
- Hacker News thread on OpenRouter routing OCR to Mistral — https://news.ycombinator.com/item?id=46330801

OCR / tesseract:
- Unstract: Guide to OCR with Tesseract — https://unstract.com/blog/guide-to-optical-character-recognition-with-tesseract-ocr/
- Nutrient: pytesseract in Python (2026) — https://www.nutrient.io/blog/how-to-use-tesseract-ocr-in-python/
- Markaicode: Tesseract in production (cost ~$0.003/page, accuracy claims) — https://markaicode.com/usecases/tesseract-use-cases-production-ai/
- Winstars.AI: structured-document extraction with Tesseract + OpenCV — https://winstarsai.medium.com/a-brief-introduction-into-data-extraction-from-structured-documents-with-tesseract-and-opencv-671ae7b5d19f

Deterministic PDF form authoring / parsing:
- pypdf forms docs (`get_fields`, `get_form_text_fields`, `update_page_form_field_values`) — https://pypdf.readthedocs.io/en/stable/user/forms.html
- pdfrw fillable forms (`NeedAppearances`) — https://westhealth.github.io/exploring-fillable-forms-with-pdfrw.html
- "Filling PDF Forms in Python — The Right Way" — https://medium.com/@zwinny/filling-pdf-forms-in-python-the-right-way-eb9592e03dba
- opentaxforms (XFA extraction from IRS forms) — https://pypi.org/project/opentaxforms/
- PDF Oxide: XFA forms in Python (XFA vs AcroForm in IRS forms) — https://pdf.oxide.fyi/docs/guides/xfa-forms
- pdftk dump_data_fields / fill_form usage — https://blog.pythonlibrary.org/2018/05/22/filling-pdf-forms-with-python/

Reliability / hallucination on financial extraction:
- FAITH: tabular hallucination in finance — https://arxiv.org/pdf/2508.05201
- PHANTOM: hallucination detection in financial long-context QA — https://openreview.net/forum?id=5YQAo0S3Hm
- Hallucination-rate roundup (2025/2026) — https://sqmagazine.co.uk/llm-hallucination-statistics/

Model cost/capability:
- Gemini 2.5 Flash pricing/specs — https://inworld.ai/models/google-ai-studio-gemini-2-5-flash
- GPT-4o-mini vs Gemini 2.5 Flash — https://www.appaca.ai/resources/llm-comparison/gpt-4o-mini-vs-gemini-2.5-flash

Privacy / PII redaction:
- "Redact PII Before Sending Data to LLMs" — https://dev.to/raviteja_nekkalapu_/redact-pii-before-sending-data-to-llms-a-developers-guide-1j04
- Microsoft Presidio approach / DataFog — https://github.com/DataFog/datafog-python

---

## Findings

### A. LLM vision extraction via OpenRouter

**Which vision-capable models are available (June 2026).** OpenRouter exposes a large
vision-models collection. Practically relevant, low-cost, strong-at-OCR/extraction candidates:
- **Google Gemini 2.5 Flash** (and Gemini 3 Flash preview) — native JSON/schema enforcement,
  multimodal incl. PDFs, 1M context. Pricing cited around **$0.30/M input, $2.50/M output** tokens
  for 2.5 Flash. Strong document-extraction reputation. *(Confidence: high that it's available and
  vision-capable; medium on exact current price — verify on the live model page.)*
- **OpenAI GPT-4o-mini** — vision-capable, very cheap (**~$0.15/M in, $0.60/M out**), 128k context,
  supports structured outputs (GPT-4o and later). *(Confidence: high.)*
- **Anthropic Sonnet/Opus** (4.x) — image input, structured outputs (Sonnet 4.5 / Opus 4.1+). Higher
  cost; overkill for one W-2 but available. *(Confidence: high.)*
- **Qwen3-VL** (8B/32B), Gemma 3, and other open multimodal models — cheaper/free tiers exist but
  more variable on precise numeric extraction. *(Confidence: medium.)*

For a single ~$40k W-2, **per-extraction cost is a fraction of a cent** on Gemini 2.5 Flash or
GPT-4o-mini — cost is not a constraint here.

**How to get reliable structured/JSON output.** OpenRouter supports
`response_format: { type: "json_schema", json_schema: { name, strict: true, schema: {...} } }`.
Guidance: set `strict: true`, add `additionalProperties: false`, mark required fields, and give each
property a clear description. Strict schema mode is explicitly recommended for "entity extraction
with fixed fields" — exactly the W-2 case. Supported families: OpenAI (GPT-4o+), Gemini, Anthropic
(Sonnet 4.5 / Opus 4.1+), most open models, all Fireworks-provided models. You can filter the models
list with `supported_parameters=structured_outputs`, and set `require_parameters: true` in provider
prefs so OpenRouter only routes to a provider that honors the schema.
- **Important caveat:** OpenRouter's docs do **not** explicitly confirm that strict json_schema mode
  composes with **image/PDF inputs**. In practice Gemini and GPT-4o handle "image + json_schema"
  fine, but this is **not contractually documented**, so we should treat it as "very likely works,
  verify by test," and keep a plain `json_object` + manual-validate fallback. *(Confidence: medium.)*

**Image vs. PDF to the model.** Images go as `image_url` content (URL or `data:image/...;base64,`).
PDFs go as a `file` content part (`{"type":"file","file":{"filename","file_data"}}`), URL or
`data:application/pdf;base64,`. For PDFs, OpenRouter has a **file-parser plugin** with engines:
| Engine | What it does | Cost |
|---|---|---|
| `native` | passes the PDF straight to a model that supports file input | charged as input tokens |
| `mistral-ocr` | OCR for scanned/image PDFs | **~$2 / 1,000 pages** |
| `cloudflare-ai` | PDF→markdown via Cloudflare Workers AI | **free** |
| `pdf-text` | **deprecated**, auto-redirects to `cloudflare-ai` | — |
Default: native if the model supports files, else `mistral-ocr`. Parsed `annotations` are returned
and can be replayed to skip re-parsing (cost optimization). **But see the Risks section: there are
2026 reports that OpenRouter's live PDF behavior does not always match these docs.** For our
single-page fixture we can sidestep all of this by sending an **image** (PNG/JPEG render of the W-2)
to a vision model rather than relying on OpenRouter's PDF pipeline — simpler and better-documented.

**Reliability for the numbers.** This is the crux. Vision LLMs are good at reading a clean W-2, but
financial/tabular numeric extraction is a known hallucination/transcription-risk area (FAITH, PHANTOM
benchmarks; top models still cluster at 10–20% general hallucination, far lower when grounded but
**non-zero on exact digits**). For a hackathon judged on "numbers are correct" and "never
fabricated," **an LLM-vision number must never be trusted blind** — it needs a deterministic
cross-check or schema+range validation before it feeds the tax math. *(Confidence: high that blind
trust is unsafe; the mitigation is validation, not a better model.)*

**Privacy.** Sending the W-2 image/PDF to OpenRouter ships the **raw SSN** (and name/address) to a
third party — directly at odds with the NFR "lean toward keeping raw SSN out of LLM prompts." If we
go vision-first, the mitigation is to **redact the SSN region from the image before upload** (we
control the fixture layout, so we know where Box a / employee SSN sits) or to only request the
non-SSN fields. This is doable but adds work; the deterministic path avoids it entirely.

**Agentic impressiveness.** High. "Agent calls a vision tool, reads your W-2, fills the form" is the
most demo-friendly story and exercises the "tools" pillar with a real, non-trivial tool.

### B. OCR (tesseract) + parsing

- **Accuracy:** ~85–95% field-level on structured forms *after* layout tuning (preprocessing with
  OpenCV: grayscale/threshold/denoise; `--psm` page-segmentation tuning; keyword/bbox-based field
  location). On a clean, known fixture you can push higher, but **85–95% field accuracy means a real
  chance of a wrong digit in Box 1/Box 2** — unacceptable for guaranteed-core numbers without a
  cross-check. *(Confidence: high.)*
- **Cost/infra:** free, local, no PII leaves the box (privacy ✔). But tesseract is a **system binary**
  that must be installed in the Render image (apt `tesseract-ocr`), adding deploy friction on a free
  tier. *(Confidence: high.)*
- **Effort:** non-trivial parsing layer (regex/anchors to map OCR text → fields) that we'd be
  building largely to read a document **we author anyway**. Lower reliability than (A) or (C) for
  more code. **Lowest value-for-effort of the four** in this specific project, where we control the
  input. *(Confidence: high.)*
- **Agentic impressiveness:** low-to-medium (an OCR tool is a tool, but less "wow" than vision, and
  it's the part most likely to be flaky live).

### C. Author the fake W-2 as machine-readable (AcroForm fields and/or clean text layer)

Because **we** supply the fixture, we can make it trivially and deterministically parseable:
- **AcroForm option:** build the W-2 PDF with named fillable fields (e.g. `box1_wages`,
  `box2_fed_withholding`, `employee_ssn`, `employer_ein`, `box15_state`, ...). The tool reads them
  with `pypdf`: `reader.get_fields()` / `reader.get_form_text_fields()`. Deterministic, instant,
  ~100% reliable. We can read **only** the fields the tax math needs and **never load SSN into any
  prompt or log** (privacy ✔✔). *(Confidence: high.)*
- **Clean text-layer option:** generate the PDF (e.g. reportlab) with a known, unambiguous text
  layout, parse with `pdfplumber`/`pypdf` text extraction + anchored regex. Also deterministic. Field
  values are exactly the strings we wrote. *(Confidence: high.)*
- **Reliability:** the highest of all options for *our* fixture — the numbers are exactly what we
  authored; zero hallucination/OCR-error surface. Directly serves "must actually work end-to-end" and
  "numbers correct / never fabricated." *(Confidence: high.)*
- **Privacy:** best — raw SSN can be parsed code-side and dropped/masked before any LLM call or log.
- **Agentic impressiveness:** **lowest if it's the *only* path** — a judge may read it as "you just
  parsed your own file," which undercuts the "tools/agent reads a real document" story. This is the
  main reason not to ship (C) alone.
- **Note for the separate PDF-fill question (out of scope here but adjacent):** the **official IRS
  1040** PDF is a **hybrid AcroForm+XFA** form. `pypdf`/`pdftk`/`pdfplumber` read/fill the **AcroForm**
  layer (field names like `topmostSubform[0].Page1[0]...`); they have **no XFA support**. Filling the
  AcroForm fields works (pdftk can `drop_xfa`); this matters for the 1040-output tool, **not** for our
  W-2-input fixture, which we author cleanly. Flagged so the architecture phase doesn't conflate them.

### D. Hybrid (vision primary or fallback + deterministic)

Combine the strengths: deterministic parse of the authored fixture (guarantees correctness + privacy)
**and** an OpenRouter vision tool (impressiveness + robustness to "what if the judge uploads their own
messy W-2"). Two viable orderings:
- **D1 — deterministic-default, vision-fallback:** try AcroForm/text parse first; if it fails or
  fields are missing, call the vision tool. Maximizes reliability; vision is a graceful-degradation
  story. Risk: on the happy path the vision tool may never visibly fire, slightly muting the
  "agentic" demo unless we surface it in the observation trail.
- **D2 — vision-primary, deterministic cross-check/fallback:** agent calls vision tool to extract;
  code **cross-checks** against the deterministic parse of the fixture (and against schema/range
  validation), and uses the deterministic value if they disagree. Most impressive *and* still safe,
  because the deterministic value is the tie-breaker. Costs one cheap LLM call per upload.

Either way: **schema + range validation (e.g. wages in plausible bounds, withholding ≤ wages,
required boxes present) gates every number before the tax computation and PDF fill.** No fabricated
value reaches the form — satisfying the NFR and the guardrails pillar.

### Cross-cutting: ≤5-question budget

All four extraction paths return the same structured fields, so none of them *spends* a question —
extraction is automatic on upload. The question budget is for what the W-2 **doesn't** contain
(primarily **filing status**, possibly dependents). If extraction is **low-confidence** (only a risk
for B/D2), the agent might have to ask "I read your wages as $X — is that right?", which **burns a
question**. The deterministic path (C) keeps confidence ~100%, **protecting the question budget**.
This is a concrete argument for deterministic-default. *(Confidence: high.)*

### Cross-cutting: privacy / SSN

The strongest privacy posture is: **parse code-side, extract only the needed fields, redact
SSN-shaped values from logs/observation trail, and keep raw SSN out of LLM prompts.** Deterministic
parsing of an authored fixture achieves this for free. Vision extraction does not, unless we redact
the SSN region from the image first or restrict requested fields — extra work and never as clean.
Regex (`\d{3}-\d{2}-\d{4}`) reliably masks SSN in logs regardless of path. *(Confidence: high.)*

---

## Risks and Unknowns

- **OpenRouter PDF docs vs. live behavior (medium-high risk).** Multiple 2026 reports (X post Mar 26
  2026; HN thread) claim OpenRouter's live `/chat/completions` PDF parsing did **not** match the
  documented `file-parser`/engine behavior, and that OCR routing to Mistral was inconsistent.
  **Mitigation:** for our single-page W-2, send a rendered **image** to a vision model (well-trodden,
  better-documented path) instead of relying on OpenRouter's PDF pipeline; or verify the PDF path by a
  live test before committing. *Would confirm via a quick live API test against the chosen model.*
- **Strict json_schema + image input (medium).** OpenRouter docs don't explicitly guarantee strict
  structured outputs compose with vision inputs. Very likely works on Gemini 2.5 Flash / GPT-4o, but
  **unverified contractually.** *Confirm by a one-shot live test; keep a json_object + manual-validate
  fallback.*
- **Model availability/pricing drift (low-medium).** Exact model IDs and prices on OpenRouter change;
  figures here are from secondary sources. *Confirm on the live models page at build time. The
  recommendation (cheap multimodal model: Gemini 2.5 Flash or GPT-4o-mini) is robust to which exact
  one wins.*
- **Vision numeric reliability (high confidence it's non-zero).** Even good models occasionally
  misread a digit on financial forms; never trust a vision-extracted number without validation /
  cross-check. *Resolved by code-side validation gate, not by model choice.*
- **tesseract deploy friction on Render free tier (low-medium).** Requires the system package in the
  image; manageable but a moving part we don't need given (C).
- **"We authored the fixture, so deterministic parse is trivially correct" could read as
  unimpressive if shipped alone (project-risk, not technical).** Mitigated by the hybrid: keep a real,
  visible vision tool in the loop.
- **Out of scope but adjacent — 1040 *output* PDF is hybrid AcroForm+XFA.** Don't conflate with W-2
  input. Filling its AcroForm fields with pypdf/pdftk works; XFA is unsupported by those libs.
  Belongs to the PDF-fill research, flagged here to prevent a mix-up.

---

## Recommendation

**Adopt the hybrid (D).** Author the fake W-2 as a **PDF with named AcroForm fields plus a clean text
layer**. Build a single `extract_w2` agent tool that:
1. **Deterministically parses** the fixture (pypdf AcroForm fields, text-layer regex fallback),
   reading only the fields the 1040 math needs and **dropping/masking SSN** before logging.
2. **Also exposes / calls an OpenRouter vision extractor** (Gemini 2.5 Flash or GPT-4o-mini, strict
   `json_schema` structured output) — either as the primary extractor cross-checked against the
   deterministic parse (D2, most impressive), or as the fallback when deterministic parse fails (D1,
   most reliable). Pick the ordering in architecture; **D2 with deterministic tie-break** gives the
   best "agentic + correct" balance.
3. **Validates every extracted number** (schema + range/consistency checks) before it reaches the tax
   computation or the 1040 PDF. No unvalidated value is ever used.

This satisfies, in the brief's priority order: **harness quality** (a real, observable extraction
tool with enforced validation guardrails), **works end-to-end** (deterministic path can't flake on
the fixture), **numbers correct / never fabricated** (validation gate + deterministic tie-break),
**conversation quality** (high-confidence extraction protects the ≤5-question budget), and the
**privacy stance** (raw SSN parsed code-side, kept out of prompts/logs).

If forced to ship only one path under time pressure: **ship the deterministic AcroForm parse (C)** —
it is the one that guarantees the demo works and the numbers are right — and add the vision tool as
the visible "agentic" layer as soon as the core is solid.

### Smallest decision set for the orchestrator
1. **Confirm hybrid** (deterministic default + visible OpenRouter vision tool). Yes/No.
2. **Pick ordering:** D1 (vision = fallback) or D2 (vision = primary, deterministic = cross-check/
   tie-break). *(Recommend D2 for impressiveness with a safety net; D1 if minimizing LLM calls.)*
3. **Fixture format:** AcroForm fields (recommended) vs. clean text layer vs. both.
4. **Vision model:** Gemini 2.5 Flash (recommended) vs. GPT-4o-mini — confirm on live models page;
   confirm strict json_schema + image works via one live test.
5. **Send vision input as image (render of the W-2) — recommended** — vs. PDF via OpenRouter
   file-parser (riskier per the docs-vs-reality reports).
