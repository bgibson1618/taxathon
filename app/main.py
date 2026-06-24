"""Taxathon FastAPI app — substrate skeleton.

Feature routes (POST /session, POST /upload, POST /chat, GET /trace, GET /download)
are added per the FEATURES.md ledger. This skeleton establishes the app object,
loads .env (so OPENROUTER_API_KEY is present under uv run — pre-build review / F12),
and exposes a health check.
"""
from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI

# Load .env so OPENROUTER_API_KEY is available under `uv run uvicorn` and `uv run pytest`
# (it is NOT auto-loaded otherwise — pre-build review finding).
load_dotenv()

app = FastAPI(title="Taxathon", description="Agentic tax-filing assistant")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
