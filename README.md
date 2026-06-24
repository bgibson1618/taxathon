# Taxathon — Agentic Tax-Filing Assistant

A web chat that helps a person file a U.S. federal **Form 1040 (tax year 2025)** from a single
W-2 — a short, warm conversation in, a completed, downloadable 1040 out. Built for a hackathon
whose bar is a clean, observable agent **harness** (chat loop, tools, guardrails, observation).

## Status

Early discovery. Built with [KodOS](https://github.com/) — a methodology-first agentic workflow.
The current intake brief is in `INTAKE.md`.

## What this is

A small agentic system: the user shows up with a (fake) W-2 for a ~$40k/year earner, the agent
asks **no more than 5 questions** in a warm, human tone, fills out a 2025 IRS Form 1040, and lets
the user download it. The interesting part — and what the hackathon weights most heavily — is the
architecture of the harness that demonstrates four pillars **enforced and visible, not cosmetic**:
a stateful chat loop, real tools, guardrails, and an observable decision/action trail. The system
deploys to a public URL (Render or comparable). Fake data only — no real PII, no e-filing, not tax
advice.

## Getting oriented

This project follows the KodOS read order — there is no `CONTEXT.md`:

- `INTAKE.md` — the intake brief (problem, users, constraints, environment)
- `PRD.md` — product intent (once written)
- `ARCHITECTURE.md` — system shape and decisions (once written)
- `FEATURES.md` — the feature plan (once written)
- `IMPLEMENTATION.md` — current state and next step (during build)

Run `/kodos:go` to start or resume the workflow.

## Environment

Python 3.12+ via **uv** on native Linux; **FastAPI** web chat; LLM via **OpenRouter**
(`OPENROUTER_API_KEY` in `.env`). Verify with `uv run pytest`. Deploy target: Render (free tier),
with a one-command local run as fallback.
