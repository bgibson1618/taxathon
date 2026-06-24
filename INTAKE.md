# Intake — Taxathon (Agentic Tax-Filing Assistant)

> First discovery artifact. A structured brief of what we're building and why, captured with the
> user. Feeds the PRD. Authored by `/kodos:ingest` from the hackathon challenge PDF; revise it by
> hand or re-run the skill.

- **Captured:** 2026-06-24
- **Source:** `Hackathon Challenge — Build an Agentic Tax-Filing Assistant.pdf` (ingested + fidelity-verified, two lenses)
- **Status:** Draft — confirmed with the user at intake

## Problem
A person needs to file a U.S. federal income tax return (Form 1040, tax year 2025), but the
challenge is to let them do it **simply by chatting**: they arrive with a single W-2 from a job
paying ~$40,000/year, have a short friendly conversation, and walk away with a completed,
downloadable 2025 Form 1040. The real build problem is the **architecture** that gets from four
required pillars — chat loop, tools, guardrails, observation — to that end result.

## Target user / persona
The **taxpayer**: a person filing a U.S. federal return who has a single W-2 from a ~$40,000/year
job. The system must also handle different **filing statuses** (single, married, etc.). 

A separate audience — the **hackathon judge** — is the *evaluator*, not a user of the product:
they must be able to reach the deployed system at a public URL, try it end-to-end, and read the
code to see each pillar working. (Build for the taxpayer; make the harness legible for the judge.)

## What they do today
*(Not stated in the source.)* Baseline assumed: filing a simple single-W-2 return manually via
consumer tax software (TurboTax/FreeTaxUSA) or paper IRS forms — form-driven, not conversational.
The chat assistant is meant to beat that interrogative, form-filling experience. **Confirm at
sign-off.**

## Goal / what success looks like
Build a small agentic system where a user shows up with a single W-2 (~$40k/yr), has a short,
warm conversation, and walks away with a **completed 2025 Form 1040 they can download** — working
end-to-end, not a happy-path mock of one step.

## Success criteria
Concrete, checkable signals, ordered by how the brief says it will be judged:

- **Harness quality (highest-weighted).** All four pillars are realized cleanly and convincingly,
  and they are **real and enforced, not cosmetic** — *"'it's in the prompt' is weaker than 'it's
  enforced and visible.'"* The four pillars, per the brief:
  - **Chat loop** — a conversational loop that carries state across turns.
  - **Tools** — the agent takes real actions through defined tools (at minimum, one that produces
    the filled return), not just talk.
  - **Guardrails** — constraints that keep the agent on-task, safe, and bounded (what it will/won't
    do, validation of inputs, limits it respects).
  - **Observation** — the agent's behavior is observable: a judge can see its decisions and actions.
- **It actually works** — a real (fake) W-2 in, a real downloadable 1040 out, via the chat,
  end-to-end.
- **Conversation quality** — feels like a helpful human, within the **5-question budget**.
- **Soundness of decisions** — the open-item choices (below) are reasonable and defensible.
- Web-based chat a user can interact with; front end kept minimal (UI polish is **not** judged).
- A realistic **fake W-2** (~$40k earner) is supplied for testing.
- Supports changing inputs by filing status (single, married, …).
- Deployed to a **public URL** (Render or comparable free host) that a judge can reach and try.

## Vision north-star
*(Elicited field — drawn from the brief and **actively confirmed** by the user.)*

- **Feel like:** warm and human — friendly, clear, genuinely conversational. Quality of
  communication is explicitly part of the bar.
- **Unlike:** robotic, or an interrogation; a cold tax-software form. Not chatty-for-its-own-sake
  either — it respects the 5-question budget.

## Usefulness — in the user's own words
*(Elicited field — the brief's outcome, **confirmed** by the user; not yet restated in their own
words — open to restating at sign-off.)*

> A real, downloadable 1040 — a judge uploads the fake W-2, has the chat, and downloads a filled
> 2025 Form 1040. Proof it works end-to-end, not a happy-path mock.

## Constraints
Fixed and non-negotiable (from the brief's "Fixed constraints" — *"these are part of the problem.
Don't change them."*):

- **Tax form:** U.S. Federal Form 1040, **tax year 2025**.
- **Taxpayer profile:** W-2, ~$40,000/year earner.
- **Question budget:** 5 questions asked of the user (the End-Result checklist glosses this as
  *"no more than 5"*).
- **Tone:** genuinely friendly, human-quality conversation.
- **Output:** a downloadable completed form.
- **Interface:** a web chat.
- **Deployment:** publicly reachable at a live URL, on Render or a comparable free, easy host.
- **Must actually work end-to-end** — not a happy-path mock of one step.
- **Harness must demonstrate all four pillars** (chat loop, tools, guardrails, observation),
  visibly and in the code.
- **Fake data only** — a fake W-2 and test data; **no real PII, no real filings, no e-filing.**
- **Not tax advice** — educational/hackathon exercise; the agent shouldn't pretend to give it.
- **Keep it simple** — a prototype, not a product; resist scope creep ("breadth of features is not
  the goal; a working, well-architected harness is").
- **Timeframe:** hackathon — short (exact deadline not in the source; user notes time is short).

## Scope notes (in / out)
- **In:** web chat that carries state; W-2 ingest for a ~$40k earner; ≤5 questions; warm
  conversation; tools that take real actions (≥ producing the filled return); enforced + visible
  guardrails; an observable decision/action trail; filing-status variation; a downloadable 2025
  1040; deploy to a public URL; source repo; a short `DECISIONS` note.
- **Out (v1):** UI/visual polish (kept minimal); real PII; real filing / e-filing; actual tax
  advice; feature breadth / scope creep.
- **Stretch (only if core is done and solid):** handle a second filing status or a dependent
  gracefully; let the user correct an answer mid-conversation; surface the observation trail in the
  UI (not just logs); validate the W-2 input and recover from messy/partial data.

## Environment contract
The build/run environment, pinned now so preflight and verification are unambiguous later.
*(Stack, runtime, toolchain, and verification command were chosen with the user at intake — the
brief deliberately left them open; confirm the toolchain specifics at sign-off.)*

| Aspect | Value |
| --- | --- |
| **Runs where** | Public URL on **Render** (free tier) or comparable free host; one-command local run as a **fallback (not a substitute)** for the live URL. |
| **OS / shell boundary** | Native **Linux**, `bash` (not WSL). Project at `~/projects/taxathon`. |
| **Language / runtime** | **Python 3.12+**, managed with **uv**. |
| **Toolchain** | **FastAPI** + Uvicorn (web chat + API); **pytest** for tests; `uv` for deps/venv. *(Proposed — confirm.)* |
| **Verification command** | `uv run pytest` — the end-to-end test that proves W-2 in → downloadable 1040 out. *(Proposed — confirm.)* |
| **Key dependencies / services** | **OpenRouter** (LLM provider; `OPENROUTER_API_KEY` already in `.env`, gitignored); **Render** (hosting); the **IRS 2025 Form 1040** (template/fillable source — TBD); a **fake W-2 fixture**. |

## Open questions
Most are the brief's deliberately-open decisions — judged as "soundness of your decisions." The
brief's own guidance: *"If you find yourself blocked on a 'but the spec doesn't say X' — that's the
point. Make a reasonable call, document it, move on."* (→ the `DECISIONS` note.)

- **Model choice on OpenRouter** — which specific model for the agent (reasoning quality vs. cost/latency).
- **1040 production** — how the form is obtained and filled: fill the official IRS fillable PDF
  (e.g. via `pypdf`/`pdftk`) vs. generate our own — and how the downloadable file is produced.
- **W-2 ingest** — how the user supplies the (fake) W-2 (file upload + parse vs. structured input)
  and how the agent reads it.
- **Tax computation** — computed deterministically in code (safer, more defensible) vs. via the
  LLM; how accuracy is ensured for the 2025 single-W-2 case + filing-status variation.
- **Guardrail enforcement** — code/schema/validation vs. prompt (brief favors enforced + visible).
- **Conversation design** — which ≤5 questions, in what order, and how to keep it human.
- **State & sessions** — how conversation state is held across turns.
- **Hosting specifics** — Render service config; the exact one-command local run.
- **Testing** — how end-to-end "it works" is proven (the `uv run pytest` target above).
- **Hackathon deadline** — exact submission time (not in source).

---

*Next phase: **PRD** (`/kodos:prd`) turns this brief into `PRD.md`. Run `/kodos:go` to advance.*
