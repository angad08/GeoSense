#!/usr/bin/env python3
"""
GeoSense V2 — Police Station Recommendation Tool
-------------------------------------------------
Excel = source of truth for all PS and District names.
Geocoding API = real coordinates and distances.
AI = district inference only (Case 3c), never invents names or distances.

Work is done on the cheapest rung that can answer:
    fuzzy match → locality scan → geocoding → AI
Each rung only runs if the one before it could not answer, and neither API
client is constructed until its rung is actually reached.

Usage (works from any directory):
    Interactive:  python v2/app.py             (or: python -m v2.app from root)
    One-shot:     python v2/app.py --address "Madhapur Hyderabad" --district "Cyberabad"
    Help:         python v2/app.py --help
    Launcher:     python main.py [v2] [args...]  (from the project root; v2 is the default)

Environment variables — needed only by the rung that uses them:
    export GOOGLE_MAPS_API_KEY=your_key_here      (if a lookup reaches geocoding)
    export ANTHROPIC_API_KEY=sk-ant-...            (if AI_PROVIDER = "anthropic")
    export OPENAI_API_KEY=sk-...                   (if AI_PROVIDER = "openai")
    export GOOGLE_API_KEY=AI...                    (if AI_PROVIDER = "gemini")

A lookup answered by fuzzy match or locality scan needs no keys at all.
"""

import sys
from pathlib import Path

# Make the project root importable no matter how this file is launched:
# `python v2/app.py` from anywhere, or `python app.py` from inside v2/.
# Under `python -m v2.app` __package__ is set and the path is already right.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.cli import run_cli
from v2.config import AI_PROVIDER, AI_MODEL
from v2.engine import find_best_match


BANNER = [
    "GeoSense V2 — Police Station Recommendation Tool",
    f"AI: {AI_PROVIDER.upper()} — {AI_MODEL}",
    "Distances: Google Geocoding API + geodesic (WGS-84)",
    "Address required. Other fields optional.",
    "Press Enter to skip optional. Ctrl+C to quit.",
]


def main():
    run_cli(find_best_match, BANNER, epilog=__doc__)


if __name__ == "__main__":
    main()
