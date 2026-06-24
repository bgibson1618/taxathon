"""Model + environment configuration — the F12 preflight (config half).

Single source of truth for the OpenRouter API key and the pinned model ids.
Loaded eagerly at import so a missing key fails loudly and early, not as a
silent ``None`` somewhere deep in the agent loop (FEATURES F12).

Loading order
-------------
``.env`` is loaded via ``python-dotenv`` so ``OPENROUTER_API_KEY`` is present
under both ``uv run uvicorn ...`` and ``uv run pytest`` — it is *not*
auto-loaded otherwise (pre-build review / D11).

Pinned models (recorded 2026-06-24)
-----------------------------------
PRIMARY  : ``anthropic/claude-sonnet-4.6``  (Claude Sonnet-class, current)
FALLBACK : ``anthropic/claude-sonnet-4.5``  (Claude Sonnet-class, prior gen)

Both ids were selected by querying ``https://openrouter.ai/api/v1/models`` and
keeping only current Anthropic Claude models whose ``supported_parameters``
includes ``tools`` (and ``tool_choice``) — i.e. they are *tools-filtered*. The
selection is reproducible at any time via :func:`tools_capable_anthropic_models`
and asserted by :func:`assert_pinned_models_are_tools_capable`.
"""
from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

# Load .env so OPENROUTER_API_KEY is available under `uv run uvicorn` and
# `uv run pytest`. Idempotent; safe to call again from app.main / scripts.
load_dotenv()

# ---------------------------------------------------------------------------
# Pinned OpenRouter model ids (Claude Sonnet-class, tools-capable).
# ---------------------------------------------------------------------------
#: Primary model — used by the agent loop for chat + tool-calling.
PRIMARY_MODEL = "anthropic/claude-sonnet-4.6"
#: Documented fallback if the primary route is unavailable.
FALLBACK_MODEL = "anthropic/claude-sonnet-4.5"

#: Both pinned ids, primary first. The loop tries them in order.
PINNED_MODELS: tuple[str, ...] = (PRIMARY_MODEL, FALLBACK_MODEL)

#: OpenRouter API base (OpenAI-compatible).
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
#: Models discovery endpoint used to validate the pinned ids.
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"

#: The env var carrying the server-side OpenRouter key.
API_KEY_ENV = "OPENROUTER_API_KEY"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def get_api_key() -> str:
    """Return the OpenRouter API key, or fail loudly.

    Reads :data:`API_KEY_ENV` from the environment (``.env`` already loaded at
    import). Raises :class:`ConfigError` with an actionable message if the key
    is missing or empty — never returns a silent ``None`` (FEATURES F12).
    """
    key = os.environ.get(API_KEY_ENV)
    if key is None or not key.strip():
        raise ConfigError(
            f"{API_KEY_ENV} is not set. Taxathon needs an OpenRouter API key to "
            f"reach its single LLM. Add a line `{API_KEY_ENV}=sk-or-...` to the "
            f".env file at the project root (it is gitignored), then re-run. "
            f"The key is loaded via python-dotenv under both `uv run uvicorn` "
            f"and `uv run pytest`."
        )
    return key.strip()


def tools_capable_anthropic_models(
    *, timeout: float = 30.0
) -> list[dict[str, object]]:
    """Query OpenRouter and return Anthropic Claude models that support tools.

    Hits ``GET /models`` and keeps only models whose id starts with
    ``anthropic/`` and whose ``supported_parameters`` includes ``tools``. This
    is the live filter used to *pick* and to *re-validate* the pinned ids — the
    "tools-filtered" provenance the F12 criterion requires.

    Returns the raw model dicts (id, name, supported_parameters, ...).
    """
    resp = httpx.get(OPENROUTER_MODELS_URL, timeout=timeout)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    out: list[dict[str, object]] = []
    for model in data:
        model_id = model.get("id", "")
        supported = model.get("supported_parameters") or []
        if model_id.startswith("anthropic/") and "tools" in supported:
            out.append(model)
    return out


def assert_pinned_models_are_tools_capable(*, timeout: float = 30.0) -> None:
    """Verify both pinned ids still exist and are tools-capable on OpenRouter.

    Live network check (used by the smoke script / an opt-in test). Raises
    :class:`ConfigError` if either pinned id is no longer present in the
    tools-filtered Anthropic model set (ids drift over time).
    """
    capable_ids = {m["id"] for m in tools_capable_anthropic_models(timeout=timeout)}
    for model_id in PINNED_MODELS:
        if model_id not in capable_ids:
            raise ConfigError(
                f"Pinned model {model_id!r} is no longer a tools-capable "
                f"Anthropic model on OpenRouter. Re-run the F12 preflight: query "
                f"{OPENROUTER_MODELS_URL} and re-pin a current Claude Sonnet-class "
                f"id whose supported_parameters includes 'tools'."
            )
