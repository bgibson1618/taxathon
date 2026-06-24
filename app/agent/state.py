"""Server-side session state for the agent loop (F4).

The entire persistence layer is an in-memory ``SESSIONS`` dict mapping a minted
``session_id`` to a typed :class:`SessionState`. This is deliberate (ARCHITECTURE
"Source of truth: the in-memory ``SESSIONS[session_id]``"): the state is
ephemeral; losing it on restart is fine for a demo.

TTL eviction (~30 min)
----------------------
Every touch stamps ``last_seen``. Before any read/write we sweep sessions whose
``last_seen`` is older than :data:`SESSION_TTL_SECONDS` and drop them. This bounds
memory under Render's 512 MB tier — ``pdf_bytes`` (~100-300 KB each) with no
eviction would eventually OOM (cross-backend defect #5 / ARCHITECTURE).

The state is the authority for every number: the W-2's deterministically-parsed
values and the computed return live here, never in the LLM. ``messages`` carries
the OpenAI-shaped chat transcript across turns so the agent remembers earlier
answers instead of re-deriving them.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from app.tax.compute import ComputedReturn
from app.tax.constants_2025 import FilingStatus
from app.w2.extract import W2

#: Session idle TTL. A session untouched for this long is evicted on the next
#: sweep. ~30 min keeps a demo session alive across a conversation while
#: bounding memory (ARCHITECTURE: TTL bounds memory; pdf_bytes would OOM).
SESSION_TTL_SECONDS: float = 30 * 60


@dataclass
class SessionState:
    """Typed, server-side state for one chat session.

    Carried in ``SESSIONS[session_id]`` and mutated in place by the loop and the
    tools. Every correctness-bearing value (``w2``, ``computed``) is set only by
    deterministic tool code — the LLM never writes a number here.
    """

    session_id: str
    #: OpenAI-shaped chat transcript (system + user + assistant + tool messages),
    #: carried across turns so the agent remembers earlier answers.
    messages: list[dict[str, Any]] = field(default_factory=list)
    #: The deterministically-parsed W-2 (set by the ``extract_w2`` tool). The raw
    #: SSN never lives here in cleartext — ``W2`` only exposes ``masked_ssn``.
    w2: Optional[W2] = None
    #: The chosen filing status (set by the ``set_filing_status`` tool).
    filing_status: Optional[FilingStatus] = None
    #: Count of questions the agent has asked the user via ``ask_user``. The
    #: ≤5-question budget (F5) is enforced against this counter.
    questions_asked: int = 0
    #: The computed 2025 return (set by the ``compute_1040`` tool). Authoritative.
    computed: Optional[ComputedReturn] = None
    #: Structured decision/tool/guardrail records (F6 owns the schema; F4 leaves
    #: the list so records have somewhere to land). Kept generic here.
    trace: list[dict[str, Any]] = field(default_factory=list)
    #: The path on disk where this session's uploaded W-2 was stored. The
    #: ``extract_w2`` tool reads from here (the upload route / smoke writes it).
    upload_path: Optional[str] = None
    #: The filled 1040 PDF bytes (F3 fills this via its own tool; F4 only carries
    #: the slot). Sized ~100-300 KB — the reason TTL eviction exists.
    pdf_bytes: Optional[bytes] = None
    #: Wall-clock of the last touch; drives TTL eviction.
    last_seen: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Stamp ``last_seen`` so an active session is not evicted."""
        self.last_seen = time.time()

    def is_expired(self, *, now: Optional[float] = None) -> bool:
        """True if this session has been idle past :data:`SESSION_TTL_SECONDS`."""
        ref = time.time() if now is None else now
        return (ref - self.last_seen) > SESSION_TTL_SECONDS


#: The entire persistence layer: session_id -> SessionState. In-memory, ephemeral.
SESSIONS: dict[str, SessionState] = {}


def _sweep_expired(*, now: Optional[float] = None) -> int:
    """Evict idle sessions; return how many were dropped.

    Called on every create/get so memory is reclaimed lazily without a background
    thread (simpler + sufficient for a single-process demo).
    """
    ref = time.time() if now is None else now
    dead = [sid for sid, st in SESSIONS.items() if st.is_expired(now=ref)]
    for sid in dead:
        SESSIONS.pop(sid, None)
    return len(dead)


def new_session_id() -> str:
    """Mint a fresh, unguessable session id."""
    return uuid.uuid4().hex


def create_session(
    *, messages: Optional[list[dict[str, Any]]] = None
) -> SessionState:
    """Mint and register a new :class:`SessionState`.

    Sweeps expired sessions first (lazy eviction), then seeds the state with any
    initial ``messages`` (e.g. a system prompt + warm greeting).
    """
    _sweep_expired()
    sid = new_session_id()
    state = SessionState(session_id=sid, messages=list(messages or []))
    SESSIONS[sid] = state
    return state


def get_session(session_id: str) -> Optional[SessionState]:
    """Return the live session for ``session_id``, or ``None`` if absent/expired.

    Sweeps first so an expired session is reported as gone (not silently revived).
    A returned session is ``touch``-ed to keep it alive for this interaction.
    """
    _sweep_expired()
    state = SESSIONS.get(session_id)
    if state is None:
        return None
    state.touch()
    return state
