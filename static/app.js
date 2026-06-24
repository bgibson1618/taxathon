/* Taxathon chat client (F8) — vanilla JS, no framework, no build step.
 *
 * Responsibilities:
 *   - mint a session (POST /session) on load; show a cold-start "waking" hint.
 *   - send a message via POST /chat/stream and render the NDJSON event stream
 *     PROGRESSIVELY using a fetch() ReadableStream (NOT EventSource — that is
 *     GET-only and cannot carry the chat body; ARCHITECTURE Key Decision 6).
 *   - BUFFER the incoming bytes and split on newlines so a partial NDJSON chunk
 *     never breaks JSON.parse (pre-build review finding).
 *   - show a working/typing indicator during tool turns (no dead air).
 *   - upload a W-2 (POST /upload) without spending a question.
 *   - download the filled 1040 (GET /download/{sid}).
 *   - host F6's trace: poll GET /trace/{sid} and render the records.
 */
(function () {
  "use strict";

  // ---- element handles -----------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const thread = $("thread");
  const indicator = $("indicator");
  const indicatorLabel = $("indicator-label");
  const composer = $("composer");
  const messageInput = $("message");
  const sendBtn = $("send");
  const fileInput = $("file");
  const downloadBtn = $("download");
  const wakingHint = $("waking");
  const tracePanel = $("trace-panel");
  const traceBody = $("trace-body");

  // ---- session state -------------------------------------------------------
  let sessionId = null;
  let busy = false;
  let traceTimer = null;

  // ---- small DOM helpers ---------------------------------------------------
  function addMessage(role, text) {
    const el = document.createElement("div");
    el.className = "msg " + role;
    el.textContent = text || "";
    thread.appendChild(el);
    thread.scrollTop = thread.scrollHeight;
    return el;
  }

  function showIndicator(label) {
    indicatorLabel.textContent = label || "Working…";
    indicator.hidden = false;
  }

  function hideIndicator() {
    indicator.hidden = true;
  }

  function setBusy(state) {
    busy = state;
    sendBtn.disabled = state;
    messageInput.disabled = state;
  }

  // ---- session bootstrap ---------------------------------------------------
  async function startSession() {
    try {
      const res = await fetch("/session", { method: "POST" });
      if (!res.ok) throw new Error("session " + res.status);
      const data = await res.json();
      sessionId = data.session_id;
      wakingHint.hidden = true;
      if (data.greeting) addMessage("assistant", data.greeting);
      startTracePolling();
    } catch (err) {
      wakingHint.hidden = true;
      addMessage(
        "system",
        "Couldn't reach the assistant to start a session. Please refresh and try again."
      );
    }
  }

  // ---- streaming send ------------------------------------------------------
  // Read the fetch() body as a stream, buffer bytes, split on newlines, and
  // dispatch each complete NDJSON line. A partial trailing line stays in the
  // buffer until the rest arrives — so a chunk that splits a JSON object mid-way
  // never breaks parsing.
  async function sendMessage(text) {
    if (!sessionId || busy) return;
    setBusy(true);
    addMessage("user", text);
    showIndicator("Thinking…");

    let assistantEl = null; // created lazily on the first token
    const appendToken = (chunk) => {
      if (!assistantEl) assistantEl = addMessage("assistant", "");
      assistantEl.textContent += chunk;
      thread.scrollTop = thread.scrollHeight;
    };

    const handleEvent = (evt) => {
      if (!evt || typeof evt !== "object") return;
      switch (evt.type) {
        case "tool":
          // A tool is running — show a live working indicator (no dead air).
          showIndicator("Working… (" + (evt.name || "tool") + ")");
          break;
        case "token":
          hideIndicator();
          appendToken(evt.text || "");
          break;
        case "message":
          // Whole-message form (alternative to token chunks).
          hideIndicator();
          appendToken(evt.text || "");
          break;
        case "error":
          hideIndicator();
          addMessage("system", evt.message || "Something went wrong.");
          break;
        case "done":
          hideIndicator();
          // The turn may have produced a downloadable PDF (F10 path).
          refreshDownloadState();
          pollTraceOnce();
          break;
        default:
          break;
      }
    };

    try {
      const res = await fetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });

      if (res.status === 404) {
        // Session expired — mint a fresh one and tell the user calmly.
        hideIndicator();
        addMessage("system", "Your session expired. Starting a new one…");
        sessionId = null;
        await startSession();
        return;
      }
      if (!res.ok || !res.body) {
        throw new Error("chat/stream " + res.status);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Split on newlines; keep the last (possibly partial) segment buffered.
        let nl;
        while ((nl = buffer.indexOf("\n")) !== -1) {
          const line = buffer.slice(0, nl).trim();
          buffer = buffer.slice(nl + 1);
          if (!line) continue;
          try {
            handleEvent(JSON.parse(line));
          } catch (e) {
            // A malformed line should never kill the stream — skip it.
          }
        }
      }
      // Flush any trailing buffered line (stream ended without a final newline).
      const tail = buffer.trim();
      if (tail) {
        try {
          handleEvent(JSON.parse(tail));
        } catch (e) {
          /* ignore */
        }
      }
    } catch (err) {
      hideIndicator();
      addMessage(
        "system",
        "Sorry — the connection dropped. Please try sending that again."
      );
    } finally {
      hideIndicator();
      setBusy(false);
      messageInput.focus();
    }
  }

  // ---- upload --------------------------------------------------------------
  async function uploadFile(file) {
    if (!sessionId || !file) return;
    showIndicator("Uploading your W-2…");
    const form = new FormData();
    form.append("session_id", sessionId);
    form.append("file", file);
    try {
      const res = await fetch("/upload", { method: "POST", body: form });
      hideIndicator();
      if (res.status === 404) {
        addMessage("system", "Your session expired. Starting a new one…");
        sessionId = null;
        await startSession();
        return;
      }
      if (!res.ok) throw new Error("upload " + res.status);
      const data = await res.json();
      addMessage(
        "system",
        "Uploaded " + (data.filename || "your W-2") + ". Let me take a look…"
      );
      // Let the agent react to the upload (no user question needed).
      await sendMessage("I've uploaded my W-2.");
    } catch (err) {
      hideIndicator();
      addMessage("system", "Couldn't upload that file. Please try a different one.");
    }
  }

  // ---- download ------------------------------------------------------------
  async function refreshDownloadState() {
    if (!sessionId) return;
    try {
      // A HEAD-like probe: GET returns 404 until a PDF is ready.
      const res = await fetch("/download/" + sessionId, { method: "GET" });
      downloadBtn.disabled = !res.ok;
      // Don't actually consume the body here; release it.
      if (res.body && res.body.cancel) res.body.cancel();
    } catch (e) {
      downloadBtn.disabled = true;
    }
  }

  function triggerDownload() {
    if (!sessionId) return;
    // Navigate to the file URL so the browser's downloader handles it.
    window.location.href = "/download/" + sessionId;
  }

  // ---- trace panel (hosts F6) ---------------------------------------------
  function renderTrace(records) {
    if (!records || records.length === 0) {
      traceBody.innerHTML = '<p class="trace-empty">No agent activity yet.</p>';
      return;
    }
    traceBody.innerHTML = "";
    records.forEach((r) => {
      const row = document.createElement("div");
      row.className = "trace-record";

      const decision = document.createElement("span");
      decision.className = "trace-decision " + (r.decision || "");
      decision.textContent = r.decision || "?";
      row.appendChild(decision);

      if (r.tool) {
        const tool = document.createElement("span");
        tool.className = "trace-tool";
        tool.textContent = " " + r.tool;
        row.appendChild(tool);
      }
      if (r.guardrail_verdict) {
        const v = document.createElement("span");
        v.className = "trace-verdict";
        v.textContent = "  [" + r.guardrail_verdict + "]";
        row.appendChild(v);
      }
      if (r.result) {
        const result = document.createElement("span");
        result.className = "trace-result";
        result.textContent = r.result;
        row.appendChild(result);
      }
      traceBody.appendChild(row);
    });
  }

  async function pollTraceOnce() {
    if (!sessionId) return;
    try {
      const res = await fetch("/trace/" + sessionId);
      if (!res.ok) return;
      const data = await res.json();
      renderTrace(data.records || []);
    } catch (e) {
      /* trace is best-effort; ignore poll errors */
    }
  }

  function startTracePolling() {
    if (traceTimer) clearInterval(traceTimer);
    // Poll while the panel is open so the trace populates live as the agent runs.
    traceTimer = setInterval(() => {
      if (tracePanel.open) pollTraceOnce();
    }, 1500);
    pollTraceOnce();
  }

  // ---- wiring --------------------------------------------------------------
  composer.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = messageInput.value.trim();
    if (!text || busy) return;
    messageInput.value = "";
    sendMessage(text);
  });

  fileInput.addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) uploadFile(file);
    // reset so selecting the same file again re-fires change
    e.target.value = "";
  });

  downloadBtn.addEventListener("click", triggerDownload);

  tracePanel.addEventListener("toggle", () => {
    if (tracePanel.open) pollTraceOnce();
  });

  // ---- go ------------------------------------------------------------------
  startSession();
})();
