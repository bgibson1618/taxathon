"""F12 preflight — the ``test`` leg.

Proves the configuration half of the model+environment preflight:

* ``OPENROUTER_API_KEY`` loads from ``.env`` under ``uv run pytest``.
* The missing-key path fails loudly with a clear, actionable message
  (never a silent ``None``).
* A pinned primary id and a documented fallback id are recorded, and were
  selected by filtering OpenRouter's Anthropic models for ``tools`` support
  (re-validated live when the network is reachable).

Run: ``uv run pytest tests/test_config.py``
"""
from __future__ import annotations

import httpx
import pytest

from app import config


# ---------------------------------------------------------------------------
# Env key loading
# ---------------------------------------------------------------------------
def test_api_key_loads_under_pytest():
    """OPENROUTER_API_KEY is present (loaded from .env via python-dotenv)."""
    key = config.get_api_key()
    assert key, "expected a non-empty OPENROUTER_API_KEY loaded from .env"
    # The real OpenRouter key is an `sk-or-...` token; guard against a
    # placeholder leaking in without over-fitting to length.
    assert key.startswith("sk-or-"), "OPENROUTER_API_KEY does not look like an OpenRouter key"


def test_missing_key_fails_loudly(monkeypatch):
    """An unset key raises ConfigError with a clear message, not None."""
    monkeypatch.delenv(config.API_KEY_ENV, raising=False)
    with pytest.raises(config.ConfigError) as excinfo:
        config.get_api_key()
    msg = str(excinfo.value)
    assert config.API_KEY_ENV in msg
    assert ".env" in msg  # tells the operator exactly where to fix it


def test_empty_key_fails_loudly(monkeypatch):
    """A blank/whitespace key is treated as missing and fails loudly."""
    monkeypatch.setenv(config.API_KEY_ENV, "   ")
    with pytest.raises(config.ConfigError):
        config.get_api_key()


# ---------------------------------------------------------------------------
# Pinned model ids
# ---------------------------------------------------------------------------
def test_pinned_and_fallback_ids_recorded():
    """A primary and a distinct fallback Anthropic id are pinned in config."""
    assert config.PRIMARY_MODEL.startswith("anthropic/claude-")
    assert config.FALLBACK_MODEL.startswith("anthropic/claude-")
    assert config.PRIMARY_MODEL != config.FALLBACK_MODEL
    # Both pinned, primary first, exposed for the loop's fallback ordering.
    assert config.PINNED_MODELS == (config.PRIMARY_MODEL, config.FALLBACK_MODEL)
    # Sonnet-class (the architecture's locked model class).
    assert "sonnet" in config.PRIMARY_MODEL
    assert "sonnet" in config.FALLBACK_MODEL


def _network_ok() -> bool:
    try:
        httpx.get(config.OPENROUTER_MODELS_URL, timeout=10).raise_for_status()
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _network_ok(),
    reason="OpenRouter models endpoint unreachable; skipping live tools-filter check",
)
def test_pinned_ids_are_tools_filtered_live():
    """The pinned ids appear in OpenRouter's tools-capable Anthropic set.

    This is the provenance check: the ids were chosen by filtering
    ``supported_parameters`` for ``tools`` and must still pass that filter.
    """
    models = config.tools_capable_anthropic_models()
    capable_ids = {m["id"] for m in models}
    assert config.PRIMARY_MODEL in capable_ids, (
        f"{config.PRIMARY_MODEL} missing from tools-capable Anthropic models; "
        f"re-run the F12 preflight to re-pin."
    )
    assert config.FALLBACK_MODEL in capable_ids, (
        f"{config.FALLBACK_MODEL} missing from tools-capable Anthropic models; "
        f"re-run the F12 preflight to re-pin."
    )
    # Every model that passed the filter truly advertises tools support.
    for model in models:
        assert "tools" in (model.get("supported_parameters") or [])

    # The dedicated assertion helper agrees (and is the path the smoke script uses).
    config.assert_pinned_models_are_tools_capable()
