"""
GeoSense — common/api_keys.py  (shared)
----------------------------------------
Central place to read all API keys from environment variables.

Every other module imports its keys from here — no scattered
os.environ calls, and one clear error message when a key is missing.

Set your keys before running (only the rung that uses them needs them):
    export GOOGLE_MAPS_API_KEY=your_key_here    (v2 geocoding)
    export ANTHROPIC_API_KEY=sk-ant-...    (if AI_PROVIDER = "anthropic")
    export OPENAI_API_KEY=sk-...           (if AI_PROVIDER = "openai")
    export GOOGLE_API_KEY=AI...            (if AI_PROVIDER = "gemini")
"""

import os


def get_key(name, required=True):
    """
    Read a single API key from the environment.

    Args:
        name:     Environment variable name (e.g. "GOOGLE_MAPS_API_KEY").
        required: If True, raise RuntimeError when the key is missing.
                  If False, return "" instead (key is optional at import time).

    Returns:
        The key value as a string.
    """
    value = os.environ.get(name, "")

    if not value and required:
        raise RuntimeError(
            f"[ERROR] {name} not set.\n"
            f"        Run: export {name}=your_key_here"
        )

    return value


# ── Google Maps (optional at import — used for v2 geocoding) ───────────────────
# Not required here: the fuzzy and locality rungs of the ladder answer many
# lookups without ever geocoding, and they must run with no keys at all.
# Validated at the first real geocode, inside v2/geopy_distance._client().
GOOGLE_MAPS_API_KEY = get_key("GOOGLE_MAPS_API_KEY", required=False)

# ── AI providers (optional at import — only the configured one is needed) ──────
# The correct key is validated at runtime inside common/ai_client.init_ai_client().
ANTHROPIC_API_KEY = get_key("ANTHROPIC_API_KEY", required=False)
OPENAI_API_KEY    = get_key("OPENAI_API_KEY",    required=False)
GOOGLE_AI_KEY     = get_key("GOOGLE_API_KEY",    required=False)
