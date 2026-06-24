#!/usr/bin/env bash
set -uo pipefail

source "$(dirname "$0")/env.sh"

# Verbose-stream renderers (roster_render_claude / codex_verbose_render). Only invoked when verbose=1
# resolves at a backend branch; defining them is harmless otherwise. Guarded so a missing lib never
# breaks a run (the backend branches re-check the function exists before enabling verbose).
[[ -n "${ROSTER_RENDER_LIB:-}" && -f "${ROSTER_RENDER_LIB:-}" ]] && source "$ROSTER_RENDER_LIB"

# The prompt fed to the backend on a given invocation. Defaults to the composed role prompt;
# the --chat loop reassigns it per turn to a turn-specific prompt (transcript + the message to
# answer). Defined before the run_<backend> functions, which read it.
RUN_PROMPT_FILE="$PROMPT_FILE"

if [[ "$INTERACTIVE" != "1" ]]; then
  exec > >(tee -a "$TERMINAL_LOG") 2>&1
fi

now_iso() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

event() {
  local event="$1"
  local message="${2:-}"
  printf '{"ts":"%s","event":"%s","role":"%s","backend":"%s","message":"%s"}\n' \
    "$(now_iso)" "$(json_escape "$event")" "$(json_escape "$ROLE")" \
    "$(json_escape "$BACKEND")" "$(json_escape "$message")" >> "$EVENTS_FILE"
}

resolve_bin() {
  local requested="$1"
  if command -v "$requested" >/dev/null 2>&1; then
    command -v "$requested"
    return 0
  fi

  case "$requested" in
    codex|claude|agy|gemini)
      # Interactive shell to pick up version-manager PATH (nvm etc.). Grab the first
      # ABSOLUTE-path line rather than head -n1: a chatty ~/.bashrc can print banners
      # first, which head would capture instead of the binary path.
      bash -ic "command -v $requested" 2>/dev/null | grep -m1 '^/'
      ;;
  esac
}

codex_git_check_mode() {
  case "$CODEX_SKIP_GIT_REPO_CHECK" in
    1|true|yes|on) printf 'skip\n' ;;
    0|false|no|off) printf 'check\n' ;;
    auto|"")
      if git -C "$WORKSPACE" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        printf 'check\n'
      else
        printf 'skip\n'
      fi
      ;;
    *) echo "invalid CODEX_SKIP_GIT_REPO_CHECK: $CODEX_SKIP_GIT_REPO_CHECK" >&2; return 2 ;;
  esac
}

run_codex() {
  local bin
  bin="$(resolve_bin "$CODEX_AGENT_BIN")"
  [[ -n "$bin" ]] || { echo "missing executable: $CODEX_AGENT_BIN" >&2; return 127; }

  if [[ "$INTERACTIVE" == "1" ]]; then
    local prompt
    prompt="$(cat "$RUN_PROMPT_FILE")"
    local args=(-C "$WORKSPACE" --no-alt-screen --sandbox "$CODEX_SANDBOX")
    local git_check_mode
    git_check_mode="$(codex_git_check_mode)" || return $?
    if [[ "$git_check_mode" == "skip" ]]; then
      args+=(--skip-git-repo-check)
    fi
    if [[ -n "$MODEL" ]]; then
      args+=(--model "$MODEL")
    fi
    echo "Command: $bin ${args[*]} <prompt.md>"
    PATH="$(dirname "$bin"):$PATH" "$bin" "${args[@]}" "$prompt"
    return $?
  fi

  local verbose=0
  declare -F resolve_verbose >/dev/null 2>&1 && verbose="$(resolve_verbose "$ROSTER_VERBOSE" "${ROSTER_CODEX_VERBOSE:-}" "$CHAT")"
  { [[ "$verbose" == "1" ]] && command -v jq >/dev/null 2>&1 && declare -F codex_verbose_render >/dev/null 2>&1; } || verbose=0

  local args=(exec)
  [[ "$verbose" == "1" ]] && args+=(--json)              # structured event stream for the pane renderer
  args+=(-C "$WORKSPACE" --sandbox "$CODEX_SANDBOX" --output-last-message "$LAST_MSG_FILE")
  if [[ "${MCP_MODE:-strict}" == "strict" ]]; then
    args+=(-c "mcp_servers={}")   # don't inherit configured MCP servers
  fi
  # Codex's web_search tool is OFF by default in `codex exec`, so a read-only research/verify
  # delegate comes up web-BLIND -- the same footgun fixed for Claude plan-mode in v0.35.6. Enable
  # it by default; this is orthogonal to --sandbox (the filesystem sandbox stays as set, e.g.
  # read-only). Opt out with ROSTER_CODEX_WEB=0.
  case "${ROSTER_CODEX_WEB:-on}" in
    0|false|no|off) ;;
    *) args+=(-c "tools.web_search=true") ;;
  esac
  local git_check_mode
  git_check_mode="$(codex_git_check_mode)" || return $?
  if [[ "$git_check_mode" == "skip" ]]; then
    args+=(--skip-git-repo-check)
  fi
  if [[ -n "$MODEL" ]]; then
    args+=(--model "$MODEL")
  fi
  args+=(-)

  echo "Command: $bin ${args[*]}"
  if [[ "$verbose" == "1" ]]; then
    # --json streams structured events to stdout -> codex_verbose_render -> pane/terminal.log. The
    # captured deliverable is written by codex's --output-last-message fd (independent of stdout), so
    # it stays byte-identical. return ${PIPESTATUS[0]} so a codex failure isn't masked by the renderer.
    PATH="$(dirname "$bin"):$PATH" "$bin" "${args[@]}" < "$RUN_PROMPT_FILE" | codex_verbose_render
    return "${PIPESTATUS[0]}"
  fi
  PATH="$(dirname "$bin"):$PATH" "$bin" "${args[@]}" < "$RUN_PROMPT_FILE"
}

run_antigravity() {
  local bin
  bin="$(resolve_bin "$AGY_AGENT_BIN")"
  [[ -n "$bin" ]] || { echo "missing executable: $AGY_AGENT_BIN" >&2; return 127; }

  # agy (Antigravity CLI) replaced the gemini CLI. Dialect map vs the retired gemini flags:
  #   approval-mode auto_edit/yolo -> --dangerously-skip-permissions (agy has no granular modes)
  #   approval-mode plan/default   -> (omit; agy prompts, but our read-only/emit/chat agents never act)
  #   extensions-none              -> (omit; agy imports NO plugins by default, so strict MCP is free)
  #   skip-trust                   -> (omit; agy has no such flag -- folder trust is config, and run
  #                                    dirs live under $HOME, which is trusted)
  #   output-format text / prompt  -> --print (prints plain text natively)
  #   prompt-interactive           -> --prompt-interactive (unchanged)
  # agy is strict-MCP by default; 'inherit' has no per-invocation equivalent (agy's plugin model is
  # stateful), so an inherit request is surfaced as a note rather than silently honored.
  [[ "${MCP_MODE:-strict}" == "inherit" ]] && \
    echo "note: antigravity (agy) imports no plugins by default; mcp=inherit has no per-invocation equivalent, so this delegate runs with no inherited MCP/plugins." >&2
  # NOTE: headless --model is honored only while an interactive Antigravity login is live (the model
  # list is fetched per session and never persisted to disk); otherwise agy falls back to its default
  # model. We still pass --model through -- harmless when unresolved, correct when a session exists.
  local skip=()
  [[ "${ANTIGRAVITY_PERMS:-prompt}" == "skip" ]] && skip=(--dangerously-skip-permissions)

  if [[ "$INTERACTIVE" == "1" ]]; then
    local args=("${skip[@]}")
    [[ -n "$MODEL" ]] && args+=(--model "$MODEL")
    args+=(--prompt-interactive "$(cat "$RUN_PROMPT_FILE")")
    echo "Command: $bin ${skip[*]} ${MODEL:+--model $MODEL} --prompt-interactive <prompt.md>"
    (cd "$WORKSPACE" && PATH="$(dirname "$bin"):$PATH" "$bin" "${args[@]}")
    return $?
  fi

  local args=("${skip[@]}")
  [[ -n "$MODEL" ]] && args+=(--model "$MODEL")
  args+=(--print "$(cat "$RUN_PROMPT_FILE")")
  echo "Command: $bin ${skip[*]} ${MODEL:+--model $MODEL} --print <prompt.md>"
  (cd "$WORKSPACE" && PATH="$(dirname "$bin"):$PATH" "$bin" "${args[@]}") | tee "$LAST_MSG_FILE"
}

run_claude() {
  local bin
  bin="$(resolve_bin "$CLAUDE_AGENT_BIN")"
  [[ -n "$bin" ]] || { echo "missing executable: $CLAUDE_AGENT_BIN" >&2; return 127; }

  # Extra writable roots for the write-scope hook (newline-separated; avoids colon-in-path issues).
  # Only meaningful when the write guard is on; harmless (empty) otherwise. Passed inline as
  # ROSTER_WRITE_DIRS on every claude invocation below, alongside ROSTER_RUN_DIR.
  local _rwd=""
  if [[ "${CLAUDE_WRITE_GUARD:-0}" == "1" && ${#EXTRA_WRITE_DIRS[@]} -gt 0 ]]; then
    _rwd="$(printf '%s\n' "${EXTRA_WRITE_DIRS[@]}")"
  fi

  if [[ "$INTERACTIVE" == "1" ]]; then
    local prompt
    prompt="$(cat "$RUN_PROMPT_FILE")"
    local args=(--permission-mode "$CLAUDE_PERMISSION_MODE" --add-dir "$WORKSPACE" --name "$ROLE-$RUN_ID")
    local _d
    for _d in "${EXTRA_DIRS[@]+"${EXTRA_DIRS[@]}"}"; do args+=(--add-dir "$_d"); done
    if [[ "${MCP_MODE:-strict}" == "strict" ]]; then
      args+=(--strict-mcp-config --mcp-config '{"mcpServers":{}}')   # no inherited MCP servers (claude requires the mcpServers key; bare {} is rejected)
    fi
    if [[ -n "${CLAUDE_ALLOWED_TOOLS:-}" ]]; then
      args+=(--allowedTools "$CLAUDE_ALLOWED_TOOLS")   # dontAsk needs an explicit allowlist
    fi
    if [[ "${CLAUDE_WRITE_GUARD:-0}" == "1" ]]; then
      args+=(--settings "{\"hooks\":{\"PreToolUse\":[{\"matcher\":\"Write|Edit|MultiEdit|NotebookEdit\",\"hooks\":[{\"type\":\"command\",\"command\":\"python3 $WRITE_SCOPE_HOOK\"}]}]}}")
    fi
    if [[ -n "$MODEL" ]]; then
      args+=(--model "$MODEL")
    fi
    echo "Command: $bin ${args[*]} <prompt.md>"
    (cd "$WORKSPACE" && ROSTER_RUN_DIR="$ROLE_DIR" ROSTER_WRITE_DIRS="$_rwd" PATH="$(dirname "$bin"):$PATH" "$bin" "${args[@]}" "$prompt")
    return $?
  fi

  local verbose=0
  declare -F resolve_verbose >/dev/null 2>&1 && verbose="$(resolve_verbose "$ROSTER_VERBOSE" "${ROSTER_CLAUDE_VERBOSE:-}" "$CHAT")"
  { [[ "$verbose" == "1" ]] && command -v jq >/dev/null 2>&1 && declare -F roster_render_claude >/dev/null 2>&1; } || verbose=0

  local args=(-p --permission-mode "$CLAUDE_PERMISSION_MODE" --add-dir "$WORKSPACE")
  local _d
  for _d in "${EXTRA_DIRS[@]+"${EXTRA_DIRS[@]}"}"; do args+=(--add-dir "$_d"); done
  [[ "$verbose" == "1" ]] && args+=(--output-format stream-json --verbose)   # NDJSON event stream for the renderer
  if [[ "${MCP_MODE:-strict}" == "strict" ]]; then
    args+=(--strict-mcp-config --mcp-config '{"mcpServers":{}}')   # no inherited MCP servers (claude requires the mcpServers key; bare {} is rejected)
  fi
  if [[ -n "${CLAUDE_ALLOWED_TOOLS:-}" ]]; then
    args+=(--allowedTools "$CLAUDE_ALLOWED_TOOLS")   # dontAsk needs an explicit allowlist
  fi
  if [[ "${CLAUDE_WRITE_GUARD:-0}" == "1" ]]; then
    args+=(--settings "{\"hooks\":{\"PreToolUse\":[{\"matcher\":\"Write|Edit|MultiEdit|NotebookEdit\",\"hooks\":[{\"type\":\"command\",\"command\":\"python3 $WRITE_SCOPE_HOOK\"}]}]}}")
  fi
  if [[ -n "$MODEL" ]]; then
    args+=(--model "$MODEL")
  fi

  echo "Command: $bin ${args[*]}"
  if [[ "$verbose" == "1" ]]; then
    # stream-json puts the whole NDJSON on stdout; roster_render_claude renders it to the pane AND
    # writes ONLY .result to LAST_MSG_FILE (byte-identical to text mode). return ${PIPESTATUS[0]} so a
    # claude failure isn't masked by the renderer exiting 0.
    (cd "$WORKSPACE" && ROSTER_RUN_DIR="$ROLE_DIR" ROSTER_WRITE_DIRS="$_rwd" PATH="$(dirname "$bin"):$PATH" "$bin" "${args[@]}" < "$RUN_PROMPT_FILE") | roster_render_claude "$LAST_MSG_FILE"
    return "${PIPESTATUS[0]}"
  fi
  (cd "$WORKSPACE" && ROSTER_RUN_DIR="$ROLE_DIR" ROSTER_WRITE_DIRS="$_rwd" PATH="$(dirname "$bin"):$PATH" "$bin" "${args[@]}" < "$RUN_PROMPT_FILE") | tee "$LAST_MSG_FILE"
}

# ---- --chat: conversational group-chat loop (Tier C) -------------------------
# The agent stays alive answering A2A requests addressed to it instead of doing one task and
# exiting. Turn-taking rule (runaway-safe): a turn fires ONLY on type=request to this role;
# plain inform/reply/ack/error are context only, never auto-answered. The reply is relayed
# onto the bus by this loop (the backend itself runs read-only and just generates text).

# chat_clean: strip NULs + ANSI colour codes from a captured backend reply.
chat_clean() {
  tr -d '\000' | sed 's/\x1b\[[0-9;]*m//g'
}

# chat_transcript: the recent group conversation (union of every role's inbox.jsonl in the run,
# sorted by id, last ROSTER_CHAT_HISTORY messages), rendered one per line for the turn prompt.
chat_transcript() {
  local n="${ROSTER_CHAT_HISTORY:-40}"
  cat "$RUN_DIR"/*/inbox.jsonl 2>/dev/null \
    | jq -rs --argjson n "$n" '
        sort_by(.id) | (if length > $n then .[-$n:] else . end)
        | .[] | "[\(.id)] \(.from) -> \(.to) [\(.type)]: \(.body[0:600])"' 2>/dev/null || true
}

# build_turn_prompt <request-json>: compose the per-turn prompt = base persona/contract +
# recent transcript + the specific request to answer, into $TURN_PROMPT_FILE.
build_turn_prompt() {
  local req="$1" sender body
  sender="$(printf '%s' "$req" | jq -r '.from')"
  body="$(printf '%s' "$req" | jq -r '.body')"
  {
    cat "$PROMPT_FILE"
    printf '\n\n## Recent conversation (most recent last)\n\n'
    chat_transcript
    printf '\n\n## Message to answer\n\nFrom %s (request):\n%s\n\nReply now with your message only.\n' \
      "$sender" "$body"
  } > "$TURN_PROMPT_FILE"
}

# chat_deliver <reqid> <sender> <req-json>: route the freshly-generated reply ($ROLE_DIR/last_reply.txt).
# Default: a correlated reply to the asker. Peer mode (CHAT_PEERS=1): if the reply's FIRST line is
# "@to <peer>", relay the rest to that peer as a NEW request — bounded by the hop budget (carried in
# the request subject as __hop=N) and the /gavel marker; otherwise fall back to replying to the asker.
#
# A live chat participant = a role whose per-role chat marker is "1" (it runs the --chat loop and will
# take a turn). The human peer and headless one-shot delegates are NOT, so peer relays/broadcasts must
# not target them — the request would just sit unanswered.
is_chat_participant() {  # <role>
  [[ "$(cat "$RUN_DIR/$1/chat" 2>/dev/null | tr -d '[:space:]')" == "1" ]]
}
chat_deliver() {
  local reqid="$1" sender="$2" req="$3"
  local me peers hop_limit gavel_file target relay_file inhop nexthop subject fl note corr peer d fanned
  me="$(basename "$ROLE_DIR")"
  peers="${CHAT_PEERS:-0}"; hop_limit="${HOP_LIMIT:-4}"; gavel_file="$RUN_DIR/.gavel"
  relay_file="$ROLE_DIR/last_reply.txt"; target=""

  if [[ "$peers" == "1" ]]; then
    fl="$(head -1 "$ROLE_DIR/last_reply.txt" 2>/dev/null || true)"
    if [[ "$fl" =~ ^@to[[:space:]]+(@?[A-Za-z0-9_/-]+)[[:space:]]*$ ]]; then
      target="${BASH_REMATCH[1]}"   # plain <role>, `all`, or a federated @alias[/run]/role
      tail -n +2 "$ROLE_DIR/last_reply.txt" | sed '/./,$!d' > "$ROLE_DIR/relay-body.txt"
      relay_file="$ROLE_DIR/relay-body.txt"
    fi
  fi

  # Broadcast relay (Slice B): "@to all" fans the reply to every OTHER chat participant in the room as
  # a request (same corr, hop+1) — bounded by the SAME gavel + hop budget as a direct relay (each
  # broadcast increments __hop, so a chain of re-broadcasts still dies at the limit). Each recipient
  # replies to the broadcaster; the round only continues if a recipient itself re-addresses. Self and
  # the human are never fanned to (the human drives and still sees every relay on the bus).
  if [[ "$peers" == "1" && "$target" == "all" ]]; then
    subject="$(printf '%s' "$req" | jq -r '.subject // ""')"
    inhop=0; [[ "$subject" =~ ^__hop=([0-9]+) ]] && inhop="${BASH_REMATCH[1]}"
    corr="$(printf '%s' "$req" | jq -r '.corr // ""')"; [[ -z "$corr" || "$corr" == "null" ]] && corr="$reqid"
    if [[ -f "$gavel_file" ]]; then
      rm -f "$gavel_file"; note="round ended by gavel — message the room to continue"
      { cat "$relay_file"; printf '\n\n_(%s)_\n' "$note"; } > "$ROLE_DIR/reply-final.txt"
      "$ROSTER_BIN" reply --workspace "$WORKSPACE" --from "$me" --to-msg "$reqid" "$RUN_ID" "$sender" --file "$ROLE_DIR/reply-final.txt" >/dev/null 2>&1
      echo "  round gaveled — replied to $sender instead of broadcasting"
      event "chat_gavel_stop" "gavel: suppressed broadcast; replied to $sender"
      return 0
    fi
    if (( inhop + 1 > hop_limit )); then
      note="room turn budget reached ($hop_limit hops) — message the room to continue"
      { cat "$relay_file"; printf '\n\n_(%s)_\n' "$note"; } > "$ROLE_DIR/reply-final.txt"
      "$ROSTER_BIN" reply --workspace "$WORKSPACE" --from "$me" --to-msg "$reqid" "$RUN_ID" "$sender" --file "$ROLE_DIR/reply-final.txt" >/dev/null 2>&1
      echo "  hop budget reached ($hop_limit) — replied to $sender instead of broadcasting"
      event "chat_budget" "hop budget $hop_limit reached; suppressed broadcast"
      return 0
    fi
    nexthop=$((inhop + 1)); fanned=0
    for d in "$RUN_DIR"/*/; do
      peer="$(basename "$d")"
      [[ "$peer" == "$me" || "$peer" == "human" ]] && continue
      [[ -f "$d/inbox.jsonl" ]] || continue
      is_chat_participant "$peer" || continue   # only fan to live --chat agents, not headless roles
      if "$ROSTER_BIN" send --workspace "$WORKSPACE" --from "$me" --type request --corr "$corr" --subject "__hop=$nexthop" "$RUN_ID" "$peer" --file "$relay_file" >/dev/null 2>&1; then
        fanned=$((fanned + 1))
      fi
    done
    if (( fanned > 0 )); then
      echo "  → broadcast to $fanned peer(s) (hop $nexthop, corr $corr)"
      event "chat_broadcast" "broadcast to $fanned peers (hop $nexthop, corr $corr) re $reqid from $sender"
      return 0
    fi
    # No other peers to broadcast to — don't lose the message; fall through to reply-to-asker.
    event "chat_bad_target" "@to all matched no other peers; replied to $sender instead"
    target=""
  fi

  # Federated peer relay (Slice C): "@to @alias/role" relays to a chat participant in ANOTHER
  # workspace. The federated `send` stamps our origin, so the remote agent's ordinary reply-to-asker
  # routes home via Slice B's reply routing — the remote loop needs no change. Hop budget + gavel are
  # enforced here (locally); the hop rides the __hop subject across the boundary, so a cross-workspace
  # chain still dies at the limit. Needs bidirectional federation (each room send+accept the other).
  if [[ "$peers" == "1" && "$target" == @* ]]; then
    subject="$(printf '%s' "$req" | jq -r '.subject // ""')"
    inhop=0; [[ "$subject" =~ ^__hop=([0-9]+) ]] && inhop="${BASH_REMATCH[1]}"
    corr="$(printf '%s' "$req" | jq -r '.corr // ""')"; [[ -z "$corr" || "$corr" == "null" ]] && corr="$reqid"
    if [[ -f "$gavel_file" ]]; then
      rm -f "$gavel_file"; note="round ended by gavel — message the room to continue"
      { cat "$relay_file"; printf '\n\n_(%s)_\n' "$note"; } > "$ROLE_DIR/reply-final.txt"
      "$ROSTER_BIN" reply --workspace "$WORKSPACE" --from "$me" --to-msg "$reqid" "$RUN_ID" "$sender" --file "$ROLE_DIR/reply-final.txt" >/dev/null 2>&1
      echo "  round gaveled — replied to $sender instead of relaying to $target"
      event "chat_gavel_stop" "gavel: suppressed federated relay to $target; replied to $sender"
      return 0
    fi
    if (( inhop + 1 > hop_limit )); then
      note="room turn budget reached ($hop_limit hops) — message the room to continue"
      { cat "$relay_file"; printf '\n\n_(%s)_\n' "$note"; } > "$ROLE_DIR/reply-final.txt"
      "$ROSTER_BIN" reply --workspace "$WORKSPACE" --from "$me" --to-msg "$reqid" "$RUN_ID" "$sender" --file "$ROLE_DIR/reply-final.txt" >/dev/null 2>&1
      echo "  hop budget reached ($hop_limit) — replied to $sender instead of relaying to $target"
      event "chat_budget" "hop budget $hop_limit reached; suppressed federated relay to $target"
      return 0
    fi
    nexthop=$((inhop + 1))
    if "$ROSTER_BIN" send --workspace "$WORKSPACE" --from "$me" --type request --corr "$corr" --subject "__hop=$nexthop" "$RUN_ID" "$target" --file "$relay_file" >/dev/null 2>&1; then
      echo "  → relayed cross-workspace to $target (hop $nexthop, corr $corr)"
      event "chat_federated_relay" "relayed to $target (hop $nexthop, corr $corr) re $reqid from $sender"
      return 0
    fi
    # Federated relay failed (unknown alias / not allowed / no live run) — don't lose the message.
    event "chat_bad_target" "federated @to '$target' relay failed; replied to $sender instead"
    target=""
  fi

  # Peer relay: a valid, non-self target that is a LIVE CHAT PARTICIPANT (has an inbox + chat marker)
  # in this run — never a headless role or the human, which wouldn't take a turn.
  if [[ "$peers" == "1" && -n "$target" && "$target" != "$me" && -f "$RUN_DIR/$target/inbox.jsonl" ]] && is_chat_participant "$target"; then
    subject="$(printf '%s' "$req" | jq -r '.subject // ""')"
    inhop=0; [[ "$subject" =~ ^__hop=([0-9]+) ]] && inhop="${BASH_REMATCH[1]}"
    # propagate the conversation id so the whole autonomous round shares one corr (root it at the
    # first request's id when the incoming has none).
    corr="$(printf '%s' "$req" | jq -r '.corr // ""')"; [[ -z "$corr" || "$corr" == "null" ]] && corr="$reqid"
    if [[ -f "$gavel_file" ]]; then
      rm -f "$gavel_file"; note="round ended by gavel — message the room to continue"
      { cat "$relay_file"; printf '\n\n_(%s)_\n' "$note"; } > "$ROLE_DIR/reply-final.txt"
      "$ROSTER_BIN" reply --workspace "$WORKSPACE" --from "$me" --to-msg "$reqid" "$RUN_ID" "$sender" --file "$ROLE_DIR/reply-final.txt" >/dev/null 2>&1
      echo "  round gaveled — replied to $sender instead of relaying to $target"
      event "chat_gavel_stop" "gavel: suppressed relay to $target; replied to $sender"
    elif (( inhop + 1 > hop_limit )); then
      note="room turn budget reached ($hop_limit hops) — message the room to continue"
      { cat "$relay_file"; printf '\n\n_(%s)_\n' "$note"; } > "$ROLE_DIR/reply-final.txt"
      "$ROSTER_BIN" reply --workspace "$WORKSPACE" --from "$me" --to-msg "$reqid" "$RUN_ID" "$sender" --file "$ROLE_DIR/reply-final.txt" >/dev/null 2>&1
      echo "  hop budget reached ($hop_limit) — replied to $sender instead of relaying to $target"
      event "chat_budget" "hop budget $hop_limit reached; suppressed relay to $target"
    else
      nexthop=$((inhop + 1))
      if "$ROSTER_BIN" send --workspace "$WORKSPACE" --from "$me" --type request --corr "$corr" --subject "__hop=$nexthop" "$RUN_ID" "$target" --file "$relay_file" >/dev/null 2>&1; then
        echo "  → relayed to $target (hop $nexthop, corr $corr)"
        event "chat_peer_relay" "relayed to $target (hop $nexthop, corr $corr) re $reqid from $sender"
      else
        echo "warn: could not relay to '$target'" >&2
        event "chat_turn" "relay to $target failed (re $reqid)"
      fi
    fi
    return 0
  fi

  # Default: reply to the asker. An @to that named an invalid target (self/unknown) lands here — note
  # it rather than dropping it silently.
  if [[ "$peers" == "1" && -n "$target" ]]; then
    event "chat_bad_target" "@to '$target' invalid (self/unknown/not a live chat participant); replied to $sender instead"
  fi
  if "$ROSTER_BIN" reply --workspace "$WORKSPACE" --from "$me" --to-msg "$reqid" "$RUN_ID" "$sender" --file "$relay_file" >/dev/null 2>&1; then
    echo "  replied to $sender (re $reqid)"
    event "chat_turn" "answered $reqid from $sender"
  else
    echo "warn: could not deliver reply to '$sender' (no inbox in this run?)" >&2
    event "chat_turn" "reply to $sender failed (re $reqid)"
  fi
}

run_chat_loop() {
  local wait_chunk="${ROSTER_CHAT_WAIT:-30}"
  local max_turns="${ROSTER_CHAT_MAX_TURNS:-0}"
  local me new requests req reqid sender body st reply_file tstatus turns=0
  local peers="${CHAT_PEERS:-0}" gavel_file="$RUN_DIR/.gavel"
  me="$(basename "$ROLE_DIR")"
  reply_file="$ROLE_DIR/last_reply.txt"

  # Stale-cursor guard: the recv read cursor is a line number into inbox.jsonl. A reused run dir can
  # leave a cursor pointing PAST a freshly-reset inbox — the line numbers no longer line up, so every
  # new request gets silently masked (recv sees "nothing past the cursor"). If the saved cursor is
  # beyond the current inbox, it can only be stale: reset it to 0 so we read from the top.
  local _inbox="$ROLE_DIR/inbox.jsonl" _cursor="$ROLE_DIR/.inbox.jsonl.cursor" _cur _lines
  if [[ -f "$_cursor" ]]; then
    _cur="$(cat "$_cursor" 2>/dev/null)"; [[ "$_cur" =~ ^[0-9]+$ ]] || _cur=0
    _lines="$(wc -l < "$_inbox" 2>/dev/null || printf 0)"; _lines="${_lines//[^0-9]/}"; [[ -n "$_lines" ]] || _lines=0
    (( _cur > _lines )) && printf '0\n' > "$_cursor"
  fi

  printf 'running\n' > "$STATUS_FILE"
  event "chat_started" "group chat loop; answering requests as $me"
  echo "Group chat: participant '$me' in run '$RUN_ID'. Waiting for requests (Ctrl-C or 'agent-roster stop' to leave)."

  while :; do
    st="$(cat "$STATUS_FILE" 2>/dev/null || true)"
    case "$st" in stopped|leaving|done) break ;; esac

    # Block until something new lands (advances our read cursor over everything seen). A timeout
    # returns empty -> loop and re-check the stop sentinel.
    new="$("$ROSTER_BIN" recv --workspace "$WORKSPACE" --wait --timeout "$wait_chunk" --json "$RUN_ID" "$me" 2>/dev/null || true)"
    [[ -n "$new" ]] || continue

    # Only requests addressed to us trigger a turn; everything else was just ingested as context.
    requests="$(printf '%s\n' "$new" | jq -c 'select(.type=="request")' 2>/dev/null || true)"
    [[ -n "$requests" ]] || continue

    # Peer mode: a /gavel anywhere in this batch force-ends the round — set the marker up front so any
    # relay we'd otherwise fire this batch is suppressed before we process the turn.
    if [[ "$peers" == "1" ]] && printf '%s\n' "$requests" | jq -e 'select(.body=="/gavel")' >/dev/null 2>&1; then
      : > "$gavel_file"
    fi

    while IFS= read -r req; do
      [[ -n "$req" ]] || continue
      reqid="$(printf '%s' "$req" | jq -r '.id')"
      sender="$(printf '%s' "$req" | jq -r '.from')"
      body="$(printf '%s' "$req" | jq -r '.body')"

      # Operator control: a request body of exactly /leave ends this agent's participation.
      if [[ "$body" == "/leave" ]]; then
        echo "Received /leave from $sender; leaving the chat."
        event "chat_left" "left on /leave from $sender"
        printf 'leaving\n' > "$STATUS_FILE"
        break
      fi
      # Peer mode: /gavel pauses the autonomous round (marker already set above); don't take a turn.
      if [[ "$peers" == "1" && "$body" == "/gavel" ]]; then
        echo "Received /gavel from $sender; ending the autonomous round."
        event "chat_gavel" "round force-ended by $sender"
        continue
      fi
      # A fresh human/orchestrator message clears any stale gavel (re-seed → budget refreshes).
      if [[ "$peers" == "1" && ( "$sender" == "human" || "$sender" == "orchestrator" ) ]]; then
        rm -f "$gavel_file"
      fi

      echo
      echo "-- turn: answering request $reqid from $sender --"
      build_turn_prompt "$req"
      : > "$LAST_MSG_FILE"
      tstatus=0
      if [[ -n "${ROSTER_CHAT_BACKEND_CMD:-}" ]]; then
        # Test/override hook: a command that reads the turn prompt on stdin and writes the reply
        # to stdout. Lets the loop be exercised without a live LLM backend.
        bash -c "$ROSTER_CHAT_BACKEND_CMD" < "$TURN_PROMPT_FILE" > "$LAST_MSG_FILE" 2>/dev/null || tstatus=$?
      else
        RUN_PROMPT_FILE="$TURN_PROMPT_FILE"
        case "$BACKEND" in
          codex) run_codex || tstatus=$? ;;
          antigravity) run_antigravity || tstatus=$? ;;
          claude) run_claude || tstatus=$? ;;
          *) echo "unsupported backend: $BACKEND" >&2; tstatus=2 ;;
        esac
        RUN_PROMPT_FILE="$PROMPT_FILE"
      fi

      chat_clean < "$LAST_MSG_FILE" > "$reply_file"
      if [[ ! -s "$reply_file" ]]; then
        echo "warn: empty reply for $reqid (backend status $tstatus); not sending" >&2
        event "chat_turn" "empty reply for $reqid from $sender (skipped)"
      else
        chat_deliver "$reqid" "$sender" "$req"
      fi

      turns=$((turns + 1))
      if (( max_turns > 0 && turns >= max_turns )); then
        echo "Reached chat turn budget ($max_turns); ending."
        event "chat_done" "turn budget $max_turns reached"
        printf 'done\n' > "$STATUS_FILE"
        break
      fi
    done <<< "$requests"
  done

  st="$(cat "$STATUS_FILE" 2>/dev/null || true)"
  case "$st" in
    stopped|done) ;;          # already terminal
    *) printf 'done\n' > "$STATUS_FILE" ;;
  esac
  event "finished" "chat loop ended after $turns turn(s)"
  echo
  echo "Chat ended after $turns turn(s). Status: $(cat "$STATUS_FILE" 2>/dev/null || true)"
  return 0
}

echo "Observable agent run"
echo "  run: $RUN_ID"
echo "  role: $ROLE"
echo "  backend: $BACKEND"
echo "  workspace: $WORKSPACE"
echo "  prompt: $PROMPT_FILE"
echo "  output: $OUTPUT_FILE"
echo "  log: $TERMINAL_LOG"
echo

# --chat: run the conversational loop instead of the one-shot backend invocation.
if [[ "${CHAT:-0}" == "1" ]]; then
  run_chat_loop
  cs=$?
  echo "Status: $(cat "$STATUS_FILE" 2>/dev/null || true)"
  echo "Events: $EVENTS_FILE"
  if [[ "$KEEP_OPEN" == "1" ]]; then
    echo
    echo "Pane kept open. Type exit to close it."
    exec bash -l
  fi
  exit "$cs"
fi

printf 'running\n' > "$STATUS_FILE"
event "started" "backend command starting"

status=0
case "$BACKEND" in
  codex) run_codex || status=$? ;;
  antigravity) run_antigravity || status=$? ;;
  claude) run_claude || status=$? ;;
  *) echo "unsupported backend: $BACKEND" >&2; status=2 ;;
esac

# output.md is the agent's own deliverable (it writes there per the Observable Session
# Contract). Each backend's last-message / stdout capture goes to LAST_MSG_FILE so it can
# never clobber output.md. If the agent wrote nothing itself, fall back to the capture.
if [[ ! -s "$OUTPUT_FILE" && -s "${LAST_MSG_FILE:-}" ]]; then
  cp "$LAST_MSG_FILE" "$OUTPUT_FILE"
fi

if [[ "$status" -eq 0 && "$INTERACTIVE" == "1" && ! -s "$OUTPUT_FILE" ]]; then
  printf 'done-no-output\n' > "$STATUS_FILE"
  event "finished" "interactive backend exited without output file"
  echo
  echo "Interactive backend exited without writing output.md."
  echo "Use the terminal log as the observable transcript."
elif [[ "$status" -eq 0 && ! -s "$OUTPUT_FILE" ]]; then
  status=3
  echo "Backend exited 0 but produced an empty output file: $OUTPUT_FILE" >&2
fi

if [[ "$status" -eq 0 && "$(cat "$STATUS_FILE")" == "done-no-output" ]]; then
  :
elif [[ "$status" -eq 0 ]]; then
  printf 'done\n' > "$STATUS_FILE"
  event "finished" "backend command completed"
  echo
  echo "Observable agent completed."
else
  printf 'failed\n' > "$STATUS_FILE"
  event "failed" "backend command failed with exit code $status"
  echo
  echo "Observable agent failed with exit code $status."
fi

echo "Status: $(cat "$STATUS_FILE")"
echo "Output: $OUTPUT_FILE"
echo "Events: $EVENTS_FILE"

if [[ "$KEEP_OPEN" == "1" ]]; then
  echo
  echo "Pane kept open. Type exit to close it."
  exec bash -l
fi

exit "$status"
