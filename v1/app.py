#!/usr/bin/env python3
"""
GeoSense V1 — Police Station Recommendation Tool
-------------------------------------------------
Excel = source of truth.
AI   = reasoning only (PS ranking + district inference), no internet search.
Final answer always comes from the Excel file.

Usage (works from any directory):
    Interactive:  python v1/app.py             (or: python -m v1.app from root)
    One-shot:     python v1/app.py --address "Madhapur Hyderabad" --ps "Gachibowli"
    Help:         python v1/app.py --help
    Launcher:     python main.py v1 [args...]  (from the project root)

Set the matching API key (only needed if a lookup reaches the AI rung):
    export ANTHROPIC_API_KEY=sk-ant-...            (if AI_PROVIDER = "anthropic")
    export OPENAI_API_KEY=sk-...                   (if AI_PROVIDER = "openai")
    export GOOGLE_API_KEY=AI...                    (if AI_PROVIDER = "gemini")

A lookup answered by fuzzy match or locality scan needs no keys at all.
"""

import sys
from pathlib import Path

# Make the project root importable no matter how this file is launched:
# `python v1/app.py` from anywhere, or `python app.py` from inside v1/.
# Under `python -m v1.app` __package__ is set and the path is already right.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import AI_PROVIDER, AI_MODEL
from common.cli import run_cli
from v1.engine import find_best_match


BANNER = [
    "GeoSense V1 — Police Station Recommendation Tool",
    f"AI: {AI_PROVIDER.upper()} — {AI_MODEL}",
    "Ranking: AI reasoning (distances are AI estimates)",
    "Address required. Other fields optional.",
    "Press Enter to skip optional. Ctrl+C to quit.",
]


def main():
    run_cli(find_best_match, BANNER, epilog=__doc__)


if __name__ == "__main__":
    main()
