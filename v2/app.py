#!/usr/bin/env python3
"""
GeoSense V2 — Police Station Recommendation Tool
-------------------------------------------------
Excel = source of truth for station names and stored coordinates.
An address is geocoded once; v2 shows the three nearest located station rows
within the detected state. Applicant-supplied station/district names are hints.
Without an address, a typed station name can still be looked up locally.

Usage (works from any directory):
    Interactive:  python v2/app.py             (or: python -m v2.app from root)
    One-shot:     python v2/app.py --address "Madhapur Hyderabad" --district "Cyberabad"
    Help:         python v2/app.py --help
    Launcher:     python main.py [v2] [args...]  (from the project root; v2 is the default)

Environment variables — needed only by the rung that uses them:
    export GOOGLE_MAPS_API_KEY=your_key_here      (if a lookup reaches geocoding)
An address lookup needs a Google Maps key. A name-only lookup needs no key.
"""

import sys
from pathlib import Path

# Make the project root importable no matter how this file is launched:
# `python v2/app.py` from anywhere, or `python app.py` from inside v2/.
# Under `python -m v2.app` __package__ is set and the path is already right.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.cli import run_cli
from v2.engine import find_best_match
from v2.geopy_distance import configure_workbook


BANNER = [
    "GeoSense V2 — Police Station Recommendation Tool",
    "Ranking: three nearest located stations for an address",
    "Distances: Google Geocoding API + geodesic (WGS-84)",
    "Address required. Other fields optional.",
    "Press Enter to skip optional. Ctrl+C to quit.",
]


def main():
    run_cli(find_best_match, BANNER, epilog=__doc__,
            configure_workbook=configure_workbook)


if __name__ == "__main__":
    main()
