"""F8 tests — streaming chat UI + minimal web page routes.

These exercise the HTTP surface F8 adds on the real FastAPI app via TestClient,
with the LLM patched to a deterministic fake (no network — the live `observed`
leg drives the real model). They assert the F8 success criteria:

  * GET /                      serves the chat page.
  * /static/{app.js,style.css} are mounted and served.
  * POST /upload               stores the file at state.upload_path; 0 questions; 404 no session.
  * POST /chat/stream          emits NDJSON tool + token + done events, over POST.
  * The byte stream can be buffered + split on newlines (partial chunks safe).
  * GET /trace/{sid}           returns the live records.
  * GET /download/{sid}        404s with no PDF; serves application/pdf when present.

Run: ``uv run pytest tests/test_ui.py``
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.agent import loop, state, tools

FIXTURE_W2 = Path(__file__).resolve().parent.parent / "fixtures" / "fake_w2.pdf"


# ---------------------------------------------------------------------------
# A scripted fake LLM (mirrors tests/test_agent.py) so /chat/stream runs the
# real loop + real tools without touching the network.
# ---------------------------------------------------------------------------
def _tool_call(call_id: str, name: str, args: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _resp_tool_calls(calls: list[dict]) -> dict:
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": "", "tool_calls": calls},
            }
        ]
    }


def _resp_text(text: str) -> dict:
    return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": text}}]}


class ScriptedLLM:
    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.calls = 0

    def __call__(self, messages, **kwargs):
        self.calls += 1
        if not self._responses:
            raise AssertionError("ScriptedLLM ran out of responses")
        return self._responses.pop(0)


@pytest.fixture()
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean_sessions():
    state.SESSIONS.clear()
    tools.set_guardrail_hook(tools._default_guardrail_hook)
    yield
    state.SESSIONS.clear()
    tools.set_guardrail_hook(tools._default_guardrail_hook)


@pytest.fixture()
def patch_llm(monkeypatch):
    """Install a scripted LLM into the loop module the stream route calls through."""

    def _install(responses: list[dict]) -> ScriptedLLM:
        fake = ScriptedLLM(responses)
        monkeypatch.setattr(loop, "chat_completion", fake)
        return fake

    return _install


# ---------------------------------------------------------------------------
# The page + static assets.
# ---------------------------------------------------------------------------
def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "<title>Taxathon" in body
    # Hosts the trace panel (F6) and the cold-start hint (F8).
    assert "Show agent trace" in body
    assert 'id="waking"' in body


def test_static_assets_mounted(client):
    js = client.get("/static/app.js")
    css = client.get("/static/style.css")
    assert js.status_code == 200
    assert css.status_code == 200
    # The stream reader must buffer + split on newlines (pre-build review).
    assert "indexOf" in js.text and "getReader" in js.text
    # Streams via a POST fetch(), NOT a GET-only EventSource — the client never
    # *constructs* an EventSource (a comment may name it to explain the choice).
    assert "new EventSource" not in js.text
    assert "/chat/stream" in js.text


def test_existing_routes_preserved(client):
    """F8 must keep /health, /session, /chat, /trace working."""
    assert client.get("/health").json() == {"status": "ok"}
    s = client.post("/session")
    assert s.status_code == 200
    sid = s.json()["session_id"]
    assert s.json()["greeting"]
    # /trace works on the fresh session.
    t = client.get(f"/trace/{sid}")
    assert t.status_code == 200
    assert t.json()["session_id"] == sid


# ---------------------------------------------------------------------------
# POST /upload — stores the file, spends zero questions, 404 with no session.
# ---------------------------------------------------------------------------
def test_upload_stores_file_and_spends_zero_questions(client):
    sid = client.post("/session").json()["session_id"]
    before = state.SESSIONS[sid].questions_asked

    data = FIXTURE_W2.read_bytes()
    r = client.post(
        "/upload",
        data={"session_id": sid},
        files={"file": ("fake_w2.pdf", data, "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == sid
    assert body["size"] == len(data)

    st = state.SESSIONS[sid]
    # The upload seam is set so extract_w2 finds it.
    assert st.upload_path is not None
    assert Path(st.upload_path).exists()
    assert Path(st.upload_path).read_bytes() == data
    # Zero questions spent by an upload (F8).
    assert st.questions_asked == before == 0


def test_upload_extract_w2_reads_stored_file(client):
    """The stored upload is what extract_w2 reads — end-to-end through the seam."""
    sid = client.post("/session").json()["session_id"]
    client.post(
        "/upload",
        data={"session_id": sid},
        files={"file": ("fake_w2.pdf", FIXTURE_W2.read_bytes(), "application/pdf")},
    )
    st = state.SESSIONS[sid]
    result = tools.dispatch(st, "extract_w2", "{}")
    assert result["ok"] is True
    assert st.w2 is not None and st.w2.wages > 0


def test_upload_404_without_session(client):
    r = client.post(
        "/upload",
        data={"session_id": "nope"},
        files={"file": ("w2.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /chat/stream — NDJSON tool + token + done events over POST.
# ---------------------------------------------------------------------------
def _parse_ndjson(raw: bytes) -> list[dict]:
    """Buffer-and-split parse, mirroring the browser client (newline-delimited)."""
    events = []
    buffer = ""
    # feed the bytes in small slices to prove partial-chunk safety.
    text = raw.decode()
    for i in range(0, len(text), 7):
        buffer += text[i : i + 7]
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line:
                events.append(json.loads(line))
    tail = buffer.strip()
    if tail:
        events.append(json.loads(tail))
    return events


def test_chat_stream_emits_tool_token_done(client, patch_llm):
    """A real loop run (extract_w2 -> set_filing_status -> compute_1040 -> reply)
    over POST emits NDJSON tool progress events, token chunks, then done."""
    patch_llm(
        [
            _resp_tool_calls([_tool_call("c1", "extract_w2", {})]),
            _resp_tool_calls([_tool_call("c2", "set_filing_status", {"filing_status": "single"})]),
            _resp_tool_calls([_tool_call("c3", "compute_1040", {})]),
            _resp_text("All set — you're getting a refund!"),
        ]
    )
    sid = client.post("/session").json()["session_id"]
    # Stage the W-2 so extract_w2 succeeds.
    client.post(
        "/upload",
        data={"session_id": sid},
        files={"file": ("fake_w2.pdf", FIXTURE_W2.read_bytes(), "application/pdf")},
    )

    r = client.post("/chat/stream", json={"session_id": sid, "message": "I'm single."})
    assert r.status_code == 200
    assert "application/x-ndjson" in r.headers["content-type"]

    events = _parse_ndjson(r.content)
    types = [e["type"] for e in events]

    # Tool progress events fired (working indicator, no dead air).
    tool_names = [e["name"] for e in events if e["type"] == "tool"]
    assert tool_names == ["extract_w2", "set_filing_status", "compute_1040"]

    # Token chunks reassemble to the final assistant message.
    text = "".join(e["text"] for e in events if e["type"] == "token")
    assert text == "All set — you're getting a refund!"

    # Terminated with a single done event carrying the tools fired.
    assert types[-1] == "done"
    done = events[-1]
    assert done["session_id"] == sid
    assert done["tool_calls"] == ["extract_w2", "set_filing_status", "compute_1040"]


def test_chat_stream_plain_text_turn(client, patch_llm):
    """A no-tool turn streams just token chunks + done (no tool events)."""
    patch_llm([_resp_text("Hi! Upload your W-2 whenever you're ready.")])
    sid = client.post("/session").json()["session_id"]
    r = client.post("/chat/stream", json={"session_id": sid, "message": "hello"})
    events = _parse_ndjson(r.content)
    assert all(e["type"] != "tool" for e in events)
    text = "".join(e["text"] for e in events if e["type"] == "token")
    assert text == "Hi! Upload your W-2 whenever you're ready."
    assert events[-1]["type"] == "done"


def test_chat_stream_404_without_session(client):
    r = client.post("/chat/stream", json={"session_id": "nope", "message": "hi"})
    assert r.status_code == 404


def test_chat_stream_error_surfaces_calmly(client, monkeypatch):
    """A loop failure becomes a calm NDJSON error event, not a 500 mid-stream."""

    def boom(*a, **k):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(main, "run_turn", boom)
    sid = client.post("/session").json()["session_id"]
    r = client.post("/chat/stream", json={"session_id": sid, "message": "hi"})
    assert r.status_code == 200
    events = _parse_ndjson(r.content)
    assert any(e["type"] == "error" for e in events)
    assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# GET /trace — live records (hosts F6 in the panel).
# ---------------------------------------------------------------------------
def test_trace_populates_after_a_turn(client, patch_llm):
    patch_llm([_resp_text("Hello!")])
    sid = client.post("/session").json()["session_id"]
    client.post("/chat/stream", json={"session_id": sid, "message": "hi"})
    t = client.get(f"/trace/{sid}")
    assert t.status_code == 200
    body = t.json()
    assert body["count"] >= 1
    assert any(rec["decision"] == "talk" for rec in body["records"])


# ---------------------------------------------------------------------------
# GET /download — 404 with no PDF; serves application/pdf when present.
# ---------------------------------------------------------------------------
def test_download_404_without_pdf(client):
    sid = client.post("/session").json()["session_id"]
    r = client.get(f"/download/{sid}")
    assert r.status_code == 404


def test_download_404_without_session(client):
    r = client.get("/download/nope")
    assert r.status_code == 404


def test_download_serves_pdf_when_present(client):
    sid = client.post("/session").json()["session_id"]
    state.SESSIONS[sid].pdf_bytes = b"%PDF-1.7 fake bytes"
    r = client.get(f"/download/{sid}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == b"%PDF-1.7 fake bytes"
    assert "attachment" in r.headers.get("content-disposition", "")
