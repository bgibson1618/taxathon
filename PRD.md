# Taxathon — Product Requirements Document

> An agentic web-chat tax assistant: a person arrives with a single W-2 (~$40k/yr), has a short,
> warm conversation, and downloads a completed **2025 IRS Form 1040**. The product's real substance
> is a clean, *observable* agent harness (chat loop, tools, guardrails, observation). Every claim
> here traces to `INTAKE.md`; genuine gaps are marked as Open Questions, not invented.

- **Owner:** Brent
- **Status:** Draft v0.1
- **Last updated:** 2026-06-24
- **Source:** `INTAKE.md`

---

## 1. Goal

A person with a single W-2 can chat for a minute or two and download a completed, correct **2025
IRS Form 1040** — without touching tax forms or tax software.

## 2. User / Persona

- **Primary:** a simple-return filer — one W-2, ~$40k/year, no complex tax situation — who would
  rather answer a few friendly questions than fill out IRS forms or navigate tax software.
- **Secondary (evaluator, not a product user):** a hackathon judge who must reach the deployed
  system at a public URL, run it end-to-end, and read the code to confirm each pillar is *enforced
  and visible*, not cosmetic.

## 3. What the User Does Today

Files a basic return manually — consumer tax software (TurboTax / FreeTaxUSA) or paper IRS forms:
form-driven, interrogative, and intimidating for a simple case. *(Baseline inferred — the intake
did not state the status quo; confirm.)*

## 4. Use Cases

1. **File from a W-2 (the spine).** The user provides their (fake) W-2; the agent asks **no more
   than 5** warm questions to gather what it needs (e.g. filing status, anything the W-2 doesn't
   show), fills the 2025 Form 1040, and lets the user **download the completed PDF**.
2. **Choose filing status.** The user states their status (Single / MFJ / MFS / HoH); the agent
   applies the correct **standard deduction and 2025 brackets**, recomputing the result.
3. **Lines change with inputs.** When the user changes filing status, the agent recomputes the
   standard deduction and tax and refills the form — demonstrating the agent updating the return's
   lines. (Best-effort *extra credit* lines are a stretch goal — see §5.)
4. **Judge inspects the harness.** Pointing at the running system and the repo, a judge can see
   each pillar working: state carried across turns (chat loop), a real tool producing the return
   (tools), enforced/visible constraints (guardrails), and a legible decision/action trail
   (observation).

## 5. In Scope (v1)

- **Web chat** that carries conversation state across turns.
- **W-2 intake by file upload** — the user uploads the **supplied fake W-2 (a PDF with form fields)** and
  the agent extracts its fields deterministically. *(Image/OCR upload of arbitrary W-2s is a stretch goal —
  out of v1.)*
- **Warm conversation within a ≤5-question budget** to gather what the W-2 doesn't supply.
- **Guaranteed core computation** (must always be correct): single-W-2 wages → standard deduction
  by filing status → taxable income → tax from the **2025** bracket tables → compare to W-2
  federal withholding → **refund or amount owed**.
- **Best-effort extension (deferred to stretch):** additional 1040 credit lines (e.g. EITC) are **out of
  v1** — EITC is $0 for the locked ~$40k single profile, so the "agent changes lines" capability is shown
  instead by **filing-status variation** recomputing the standard deduction and tax.
- **Filing-status variation** (Single / MFJ / MFS / HoH) driving deduction and brackets.
- **Downloadable output:** the **official IRS 2025 Form 1040 PDF**, field-populated.
- A real agent **harness demonstrating all four pillars**, enforced and visible in code + runtime.
- **Deployed** to a public URL (Render or comparable free host); one-command local run as fallback.
- Deliverables: **source repo**, the live URL, a **realistic fake W-2 fixture**, and a short
  **`DECISIONS` note** (~half a page) covering the open-item choices.

## 6. Non-Goals

- **UI / visual polish** — front end stays minimal; not judged. *(never, for v1)*
- **Real PII, real filing, e-filing** — fake data only. *(never)*
- **Actual tax advice** — educational/hackathon exercise; the agent won't pretend to advise. *(never)*
- **Feature breadth / scope creep** — a working, well-architected harness beats more features. *(never for v1)*
- **Income beyond the single provided W-2** (e.g. a spouse's separate income for MFJ, self-employment, investments) — *(later / stretch)*
- **Itemized deductions / complex schedules** the simple case doesn't need — *(later)*
- **Stretch goals, only if the core is solid:** dependents; mid-conversation answer correction;
  the observation trail surfaced in the UI (not just logs); validating/recovering from a messy or
  partial W-2.

## 7. Success Criteria

Observable yes/no outcomes, ordered by the brief's judging weight:

- **Harness quality (highest weight):** a judge can point at the code **and** the running system
  and see each pillar *enforced and visible* — chat loop carries state; at least one real tool
  produces the filled return; guardrails are enforced (code/schema/validation, not "it's in the
  prompt") and visibly refuse out-of-bounds requests; the agent's decisions and actions are
  observable.
- **It actually works end-to-end:** upload the fake W-2 → have the chat → download a filled
  official 2025 Form 1040 — no happy-path mock of a single step.
- **Numbers are correct:** the computed 1040 lines are always correct for the inputs and **never
  fabricated** — guarded at runtime by a consistency gate, with correctness checked against published
  2025 IRS figures in tests, and the refund/owed amount shown in chat server-templated from the computed
  state (the model never authors a number).
- **Conversation quality:** feels like a helpful human, within the **5-question** budget.
- **Filing status works:** changing status visibly changes the standard deduction and tax.
- **Reachable + reproducible:** live at a public URL a judge can try; fake W-2 fixture present;
  `DECISIONS` note present.

## 8. Constraints

- **Form:** U.S. Federal **Form 1040, tax year 2025**. **Profile:** W-2, ~$40,000/year. *(fixed)*
- **Question budget:** ≤5 questions to the user. **Interface:** web chat. **Tone:** warm, human. *(fixed)*
- **Output:** a downloadable completed form. **Deploy:** public URL on Render or comparable free host. *(fixed)*
- **Fake data only; not tax advice; no e-filing.** *(fixed)*
- **Accuracy stance:** given best-effort coverage, computed tax numbers must be correct for every
  line populated; the agent must not invent values.
- **Environment:** Python 3.12+ via **uv**; **FastAPI** web app; LLM via **OpenRouter**
  (`OPENROUTER_API_KEY` in gitignored `.env`); verification `uv run pytest`; native Linux/bash.

## 9. Open Questions

Most are decisions deferred to **architecture/plan** (the brief judges "soundness of decisions"):

- **"Best-effort" boundary** — exactly which additional lines/credits are in vs. out for v1 (pin in `/kodos:plan`).
- **Tax computation method** — deterministic in code vs. via the LLM. *(Recommend code for accuracy + defensibility; resolve in architecture.)*
- **W-2 parse mechanism** — how the uploaded PDF/image is read into fields.
- **Guardrail enforcement points** — where/how each guardrail is enforced and made visible.
- **Conversation design** — which ≤5 questions, in what order (sharpened in `/kodos:nfr-ux`).
- **State / session handling** — how chat state persists across turns.
- **OpenRouter model** — which specific model for the agent.
- **Hackathon deadline** — exact submission time (not in source).
- **Status-quo baseline** (§3) — confirm the "what they do today" assumption.
