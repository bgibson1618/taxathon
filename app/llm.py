"""Thin OpenRouter chat-completions client — the F12 preflight (client half).

A deliberately small wrapper over OpenRouter's OpenAI-compatible
``POST /chat/completions`` endpoint, supporting tool-calling (``tools`` +
``tool_choice``). The hand-rolled agent loop (F4) is built on this; F12 proves
the route actually performs tool-calling before the loop relies on it.

Design notes
------------
- Synchronous ``httpx`` — the loop's tool-deciding calls are non-streamed
  request/response (ARCHITECTURE: only the final natural-language turn streams,
  which is layered on later by F8). This client returns the parsed JSON body so
  callers can inspect ``finish_reason`` / ``tool_calls`` directly.
- ``require_parameters: true`` is set in the provider routing block so
  OpenRouter only routes to providers that actually honour ``tools`` — the
  reliability lever called out in ARCHITECTURE's External Dependencies.
- The API key is sourced from :func:`app.config.get_api_key`, which fails loudly
  if it is missing.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import OPENROUTER_BASE_URL, PRIMARY_MODEL, get_api_key

#: OpenAI-compatible chat-completions endpoint.
CHAT_COMPLETIONS_URL = f"{OPENROUTER_BASE_URL}/chat/completions"

# Optional attribution headers OpenRouter recommends; harmless if unrecognized.
_REFERER = "https://github.com/taxathon"
_TITLE = "Taxathon"


class LLMError(RuntimeError):
    """Raised when the OpenRouter chat-completions call fails."""


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str = PRIMARY_MODEL,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = 1024,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Issue one OpenRouter chat-completions request and return the JSON body.

    Parameters mirror the OpenAI Chat Completions shape. When ``tools`` is
    provided, ``require_parameters`` is set so OpenRouter routes only to
    providers that honour tool-calling. Raises :class:`LLMError` on a transport
    error or a non-2xx response (with the response body for diagnosis).
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if tools is not None:
        payload["tools"] = tools
        # Only route to providers that actually support the tools parameter.
        payload["provider"] = {"require_parameters": True}
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice

    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": _REFERER,
        "X-Title": _TITLE,
    }

    try:
        resp = httpx.post(
            CHAT_COMPLETIONS_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:  # transport-level failure
        raise LLMError(f"OpenRouter request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise LLMError(
            f"OpenRouter chat-completions returned {resp.status_code}: "
            f"{resp.text[:500]}"
        )

    return resp.json()


def first_message(response: dict[str, Any]) -> dict[str, Any]:
    """Return the first choice's assistant ``message`` dict from a response."""
    choices = response.get("choices") or []
    if not choices:
        raise LLMError(f"OpenRouter response had no choices: {response!r}")
    message = choices[0].get("message")
    if message is None:
        raise LLMError(f"OpenRouter choice had no message: {choices[0]!r}")
    return message


def extract_tool_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the assistant message's ``tool_calls`` (empty list if none).

    Each tool call is OpenAI-shaped::

        {"id": "...", "type": "function",
         "function": {"name": "...", "arguments": "<json string>"}}
    """
    return first_message(response).get("tool_calls") or []
