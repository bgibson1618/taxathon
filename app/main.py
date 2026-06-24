"""Taxathon FastAPI app — substrate skeleton + F4 agent routes.

Feature routes (POST /session, POST /upload, POST /chat, GET /trace, GET /download)
are added per the FEATURES.md ledger. This skeleton establishes the app object,
loads .env (so OPENROUTER_API_KEY is present under uv run — pre-build review / F12),
and exposes a health check.

F4 adds the two agent routes:
  * POST /session — mint a session_id, seed SessionState, return a warm greeting.
  * POST /chat    — run one agent turn (non-streaming; streaming is F8).
"""
from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Load .env so OPENROUTER_API_KEY is available under `uv run uvicorn` and `uv run pytest`
# (it is NOT auto-loaded otherwise — pre-build review finding).
load_dotenv()

from app.agent import GREETING, create_session, get_session, initial_messages, run_turn

app = FastAPI(title="Taxathon", description="Agentic tax-filing assistant")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# F4 — agent routes
# ---------------------------------------------------------------------------
class SessionResponse(BaseModel):
    """Response of POST /session: the minted session id + the warm greeting."""

    session_id: str
    greeting: str


class ChatRequest(BaseModel):
    """Request of POST /chat: which session, and the user's message."""

    session_id: str
    message: str


class ChatResponse(BaseModel):
    """Response of POST /chat: the assistant's reply + which tools fired this turn."""

    session_id: str
    reply: str
    tool_calls: list[str]


@app.post("/session", response_model=SessionResponse)
def create_chat_session() -> SessionResponse:
    """Mint a new chat session, seed its SessionState, and return a warm greeting.

    The seed transcript is the system prompt + the greeting (so the agent
    remembers its own opening line); the greeting is also surfaced to the client.
    """
    state = create_session(messages=initial_messages())
    return SessionResponse(session_id=state.session_id, greeting=GREETING)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """Run one agent turn for ``req.session_id`` and return the assistant reply.

    Non-streaming here (streaming is F8). The agent may dispatch tools internally;
    only the final natural-language message is returned. A missing/expired session
    is a 404 so the client can mint a fresh one.
    """
    state = get_session(req.session_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. Start a new session via POST /session.",
        )

    result = run_turn(state, req.message)
    return ChatResponse(
        session_id=state.session_id,
        reply=result.content,
        tool_calls=result.tool_calls_made,
    )
