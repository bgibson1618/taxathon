# NFR / UX-Feel — Taxathon

> Non-functional requirements and the intended *feel* of the UX. The companion to `PRD.md`
> (what the product does); this captures **how well** it must do it and **how it should feel**.
> Authored by `/kodos:nfr-ux`. Feeds `/kodos:architect`.

- **Project type:** UI app — a **minimal web chat** (human-facing, but visuals deliberately minimal and un-judged; the experienced UX is the *conversation*)
- **Source:** `PRD.md`
- **Last updated:** 2026-06-24

---

## Part A — Non-Functional Requirements

### Performance
- **Targets:** Responses **stream** so each turn feels responsive — warm first-token ~1–2s, full
  assistant turn ≤ ~5s (LLM-bound). W-2 parse ≤ ~5s; 1040 PDF generation ≤ ~2s. **Render free-tier
  cold start ~30–60s** on the first request after idle is **accepted and documented**; the
  one-command local run is the judge's fallback.
- **Scale assumptions:** Demo-scale — at most a handful of concurrent judges; single-session focus;
  no high-throughput or large-data requirement at v1.
- **Degradation posture:** Graceful — stream/indicate progress while the LLM or a tool works; on a
  tool/LLM error, the agent surfaces a calm, plain-language message rather than crashing. Cold
  start is tolerated (signal that the service is waking).

### Security & Privacy
- **Sensitive data:** W-2 fields are PII-shaped (name, SSN, wages) but **fake only — no real PII
  permitted**. The `OPENROUTER_API_KEY` is a secret: server-side only, in gitignored `.env`, never
  sent to the client.
- **AuthN / AuthZ:** n/a — public demo, no accounts; anyone with the URL can use it.
- **Data handling:** **Ephemeral, in-memory per session** — nothing persisted to disk/DB.
  SSN-shaped values are **redacted from logs and the observation trail**. Lean toward keeping raw
  SSN **out of LLM prompts** (compute code-side); only W-2 values actually needed for reasoning go
  to OpenRouter. No other third-party data sharing.
- **Threat posture:** Minimal (demo, fake data). **Out of scope:** real auth, production PII
  protection beyond redaction, abuse/DoS hardening. **In scope:** don't leak the API key; never log
  full SSNs; guardrails keep the agent on-task (refuses non-tax/off-task requests; gives no tax
  advice).

### Reliability & Availability
- **Uptime / availability target:** Best-effort demo, **no SLA**. The live URL should be reachable
  for judging; Render free-tier sleep (cold start) is accepted, with the local-run fallback.
- **Failure handling:** The **happy path must be robust** ("must actually work end-to-end"):
  retry transient LLM errors; handle tool failures with a calm user-facing message; **validate the
  computed return before filling the PDF** (no fabricated numbers reach the form).
- **Backups / durability:** None needed — state is ephemeral; losing a session on restart is
  acceptable for a demo.

### Environment & Constraints
- **Runtime / platform:** Python 3.12+ via **uv**; native **Linux / bash**; modern evergreen
  browser front end.
- **Toolchain:** uv (deps/venv), **FastAPI + Uvicorn**, **pytest**. PDF-fill tooling for the
  official 1040 = `TBD` (architecture).
- **Deployment / distribution:** **Render** free tier (public URL); **one-command local run** as
  fallback (exact command `TBD` — architecture).
- **External dependencies & limits:** **OpenRouter** (LLM; per-account rate/cost limits — keep
  usage modest); **IRS 2025 Form 1040** fillable PDF (source `TBD`). No paid services required.
- **Compliance / licensing:** None for the exercise (not real filing, not tax advice). Use the
  official IRS form within its public-domain status.

### Accessibility *(human-facing UI — minimal, right-sized to the un-judged visual bar)*
- **Standard / target:** Reasonable defaults (not a full WCAG audit, given the minimal-UI mandate).
- **Specifics:** Keyboard-usable chat (type + Enter to submit); readable contrast; legible default
  font size; **reduced-motion respected** (the only motion is a typing indicator). i18n: English only.

---

## Part B — UX Feel
<!-- BEGIN UX-FEEL -->

> The *subjective* contract — proved later by `sign-off`. For Taxathon the UX that matters is the
> **conversation**; the visual layer is intentionally minimal.

### Tone & Personality
- **In three words:** warm, clear, reassuring.
- **Voice:** friendly, plain-language — like a helpful person, not a form. No jargon; explains in
  everyday terms; never robotic or interrogative.
- **Feeling on first use:** within 30s, "this is easy and friendly, not scary — it's going to walk
  me through it."

### Interaction Feel
- **Pace & responsiveness:** Responsive via **streaming**; visibly shows it's working (typing
  indicator / streamed tokens). Considered, not sluggish.
- **Density:** Minimal — a single conversation thread, **one clear question at a time** (within the
  ≤5-question budget); low cognitive load.
- **Error & empty states:** Calm and **guiding** — plain-language recovery ("I couldn't read the
  wages in Box 1 — what's the amount?"); the initial/empty state warmly invites the user to share
  their W-2.
- **Motion & feedback:** Minimal, functional — typing/working indicator, gentle message fade-in;
  reduced-motion honored.

### Reference Products
- **Like:** a warm human onboarding/guide — a friendly support chat or a calm guided wizard — for
  the one-thing-at-a-time pace, reassurance, and plain language. *(No single brand mandated.)*
- **Unlike:** TurboTax / traditional tax software's form-march and upsell interrogation; cold,
  robotic form-filling. *(From intake: "unlike a cold tax-software form.")*

### Look & Aesthetic *(minimal-by-design — these are the confirmed minimal defaults, not a full design pass)*
- **Palette / mood + light/dark:** Clean and calm, **light-mode**; neutral background + a single
  trustworthy accent (calm blue/green). Minimal.
- **Type scale:** One **humanist sans**, comfortable body size, modest headings — readability over
  style.
- **Spacing / density:** **Airy and simple** — generous whitespace around a centered chat column;
  uncluttered (agrees with the minimal Interaction-Feel density above).
- **Motion character:** **Minimal / reduced-motion-first** — typing indicator + a gentle message
  fade-in, nothing more.
- **Constraints:** None — no brand or design system; the front end is deliberately minimal and
  un-judged.

<!-- END UX-FEEL -->

---

## Open Questions
- **Exact one-command local run** command (architecture).
- **PDF-fill tooling** for the official 2025 1040 (architecture).
- **PII-to-LLM boundary** — confirm raw SSN stays out of prompts and tax math is computed code-side
  (architecture; security-relevant).
- **OpenRouter model + token/cost budget** (architecture).
- **Hackathon deadline** — exact submission time (still unknown).
