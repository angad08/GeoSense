"""
GeoSense — common/ai_client.py  (shared)
-----------------------------------------
AI client initialisation, lazy wrapper and call interface — identical in v1
and v2. Supports Anthropic, OpenAI, and Gemini behind one interface.

What each version does WITH the client stays per-version:
    v1/ai_engine.py — PS ranking + district inference (AI-heavy)
    v2/ai_engine.py — district inference only (AI is the last rung)
"""

import sys

from common.api_keys import ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_AI_KEY
from common.config import AI_PROVIDER, AI_MODEL


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT SETUP
# ─────────────────────────────────────────────────────────────────────────────

def init_ai_client():
    """
    Return the appropriate client object for the configured AI_PROVIDER.
    Validates that the matching API key is set.
    Exits with a clear error message if the key is missing or the
    package is not installed.
    """
    if AI_PROVIDER == "anthropic":
        try:
            import anthropic
        except ImportError:
            print("[ERROR] anthropic package not installed. Run: pip install anthropic")
            sys.exit(1)
        if not ANTHROPIC_API_KEY:
            print("[ERROR] ANTHROPIC_API_KEY not set. Run: export ANTHROPIC_API_KEY=sk-ant-...")
            sys.exit(1)
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    elif AI_PROVIDER == "openai":
        try:
            from openai import OpenAI
        except ImportError:
            print("[ERROR] openai package not installed. Run: pip install openai")
            sys.exit(1)
        if not OPENAI_API_KEY:
            print("[ERROR] OPENAI_API_KEY not set. Run: export OPENAI_API_KEY=sk-...")
            sys.exit(1)
        return OpenAI(api_key=OPENAI_API_KEY)

    elif AI_PROVIDER == "gemini":
        try:
            import google.generativeai as genai
        except ImportError:
            print("[ERROR] google-generativeai not installed. Run: pip install google-generativeai")
            sys.exit(1)
        if not GOOGLE_AI_KEY:
            print("[ERROR] GOOGLE_API_KEY not set. Run: export GOOGLE_API_KEY=AI...")
            sys.exit(1)
        genai.configure(api_key=GOOGLE_AI_KEY)
        return genai.GenerativeModel(AI_MODEL)

    else:
        print(f"[ERROR] Unknown AI_PROVIDER: '{AI_PROVIDER}'")
        print("        Choose from: 'anthropic', 'openai', 'gemini'")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# LAZY CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class LazyAgent:
    """
    Defers AI client creation until an AI call is actually needed.

    Fuzzy- and locality-only lookups (Case 1 — known PS, Case 3a — address
    names a PS) never touch the AI, so they must run with NO API key and NO
    cost. By passing a LazyAgent around instead of a live client,
    init_ai_client() — which exits when the key is missing — is only invoked
    the moment an AI path is genuinely reached.
    """
    def __init__(self):
        self._client = None

    def resolve(self):
        if self._client is None:
            self._client = init_ai_client()
        return self._client


# ─────────────────────────────────────────────────────────────────────────────
# CALL WRAPPER
# ─────────────────────────────────────────────────────────────────────────────

def call_ai(prompt, client):
    """
    Send a prompt to the AI and return the response text.
    Unified interface for Anthropic, OpenAI, and Gemini.
    Raises an exception on failure — callers handle it.

    Accepts either a live client or a LazyAgent (resolved on first use here).
    """
    if isinstance(client, LazyAgent):
        client = client.resolve()

    if AI_PROVIDER == "anthropic":
        resp = client.messages.create(
            model=AI_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    elif AI_PROVIDER == "openai":
        resp = client.chat.completions.create(
            model=AI_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()

    elif AI_PROVIDER == "gemini":
        resp = client.generate_content(prompt)
        return resp.text.strip()
