"""F12 preflight — the ``observed`` leg: one real OpenRouter tool-call round-trip.

Issues ONE live tool-calling request to the pinned primary model via
``app.llm`` with a trivial tool, and asserts a well-formed ``tool_call`` comes
back. This proves the route supports the agent loop's tool-calling *before* F4
relies on it (FEATURES F12 / DECISION_LOG D10).

Run live:
    uv run python scripts/smoke_tools.py

Exit code 0 + a printed tool_call summary == the observed leg passes. A non-zero
exit prints the exact blocker (missing key, model gone, network, no tool_call),
which becomes the F12 ``needs`` field — do NOT fake success.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the project root is importable when run as `uv run python scripts/...`
# (pytest adds it via pythonpath, a bare script does not).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, llm  # noqa: E402  (path bootstrap must precede import)

# A trivial, unambiguous tool. The prompt forces a tool call so we can assert
# the route returns the OpenAI-shaped tool_call structure the loop depends on.
SMOKE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g. 'Austin'.",
                }
            },
            "required": ["city"],
        },
    },
}

SMOKE_MESSAGES = [
    {
        "role": "system",
        "content": (
            "You are a tool-using assistant. When the user asks about weather, "
            "you MUST call the get_weather tool. Do not answer in prose."
        ),
    },
    {"role": "user", "content": "What's the weather in Austin right now?"},
]


def run_smoke() -> dict:
    """Issue the live tool-calling request and return a summary dict.

    Raises on any blocker so ``main`` can surface the exact reason.
    """
    # Fail loudly here if the key is missing — clearer than a 401 later.
    config.get_api_key()

    response = llm.chat_completion(
        SMOKE_MESSAGES,
        model=config.PRIMARY_MODEL,
        tools=[SMOKE_TOOL],
        tool_choice="required",  # force a tool call so we can assert its shape
    )

    tool_calls = llm.extract_tool_calls(response)
    if not tool_calls:
        message = llm.first_message(response)
        raise RuntimeError(
            "No tool_call returned by the pinned model. finish_reason="
            f"{(response.get('choices') or [{}])[0].get('finish_reason')!r}; "
            f"message content={message.get('content')!r}"
        )

    call = tool_calls[0]
    # Validate the tool_call is well-formed: name + JSON-parseable arguments.
    fn = call.get("function") or {}
    name = fn.get("name")
    raw_args = fn.get("arguments")
    if name != "get_weather":
        raise RuntimeError(f"Unexpected tool name in tool_call: {name!r}")
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"tool_call.arguments not valid JSON: {raw_args!r} ({exc})"
        ) from exc
    if not isinstance(args, dict) or "city" not in args:
        raise RuntimeError(
            f"tool_call arguments missing required 'city': {args!r}"
        )

    return {
        "model": response.get("model", config.PRIMARY_MODEL),
        "tool_call_id": call.get("id"),
        "tool_name": name,
        "arguments": args,
        "finish_reason": (response.get("choices") or [{}])[0].get("finish_reason"),
    }


def main() -> int:
    try:
        summary = run_smoke()
    except Exception as exc:  # noqa: BLE001 — surface the exact blocker
        print(f"SMOKE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("SMOKE PASSED — well-formed tool_call received from pinned model.")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
