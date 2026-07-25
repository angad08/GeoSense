"""
GeoSense — common/config.py  (shared base)
-------------------------------------------
Settings shared IDENTICALLY by v1 and v2. Version-specific values live in the
per-version config (see v2/config.py, which imports this base and adds its own
DISTANCE_WARN_KM). v1 needs no extra values, so it imports this module directly.

Excel file is resolved from the PROJECT ROOT (the parent of common/), so both
versions and the test harness find data/ from any working directory:

    GeoSense/                 <- project root
    ├── common/config.py      <- this file  (root = parent.parent)
    └── data/POLICE_STATION.xlsx
"""

from pathlib import Path

# ── Excel Source (resolved from project root) ──────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Use new naming convention; fall back to old if needed for compatibility
_preferred = PROJECT_ROOT / "data" / "sample_police_stations.xlsx"
_fallback = PROJECT_ROOT / "data" / "POLICE_STATION.xlsx"
EXCEL_FILE = _preferred if _preferred.exists() else _fallback
SHEET_NAME = "PoliceStation"
COL_DISTRICT = "DISTRICT"
COL_PS       = "POLICE STATION"

# ── Geocoding (v2) ─────────────────────────────────────────────────────────────
# GEOCODE_SUFFIX is appended to every station geocode query:
#     "{PS_NAME} Police Station, {DISTRICT}, {GEOCODE_SUFFIX}"
#
# Station coordinates live in the PoliceStation sheet itself, in the COL_LAT /
# COL_LNG columns, alongside the district and station name. There is no separate
# cache file: the Excel is the single source of truth.
#
# A blank LAT/LNG means "not geocoded yet". v2/geopy_distance.py geocodes those
# rows the first time they are needed and writes the result straight back into
# the sheet, so every station costs one geocode ever — and adding a station to
# the Excel needs no rebuild step. Only the user's input address is geocoded on
# a normal lookup (1 API call).
GEOCODE_SUFFIX = "Telangana, India"
COL_LAT        = "LAT"
COL_LNG        = "LNG"

# ── Matching Thresholds ────────────────────────────────────────────────────────
FUZZY_CUTOFF    = 80    # 0–100: scores below this are rejected
LOCALITY_CUTOFF = 86    # stricter cutoff for address-locality → PS/District scans
TOP_N           = 3     # number of results to return

# ── Locality-Scan Safety Knobs ─────────────────────────────────────────────────
# These two constants make the "junk token wins by sheet order" failure shape
# structurally impossible in the address-locality scan (matcher.py, rungs 3a/3b).
#
# MIN_LOCALITY_LEN — minimum number of significant characters a candidate
#   locality must have before it is allowed to be fuzzy-matched at all. A door
#   number fragment like "H" (1 char) carries no geographic signal and must
#   never become a candidate. Applied uniformly to every candidate, whether a
#   lone word or a joined multi-word segment.
#
# MAX_TIE_WIDTH — if more than this many police stations (or districts) tie at
#   the top score, the whole locality scan is treated as a null result and the
#   query falls through to the next rung. A tie that wide is not a ranking; it
#   is the signature of a token that matches everything (i.e. matches nothing),
#   so picking any of them — by sheet order or otherwise — would be noise.
MIN_LOCALITY_LEN = 4    # candidates shorter than this are never considered
MAX_TIE_WIDTH    = 5    # a top-score tie wider than this → null result

# ── Lookup Results Log ─────────────────────────────────────────────────────────
# Completed lookups are appended to this sheet inside the same workbook.
# The sheet already exists as "Sheet1"; it is renamed to LOG_SHEET_NAME on first
# write and reused from then on.
LOG_SHEET_NAME = "LookupResults"
LOG_OLD_SHEET  = "Sheet1"
LOG_COLS       = ["ADDRESS", "RESULT LOOKUP", "RESULT MATCH"]

# ── AI Provider ───────────────────────────────────────────────────────────────
# Set AI_PROVIDER to switch between providers.
# Matching API key must be set as an environment variable.
#
#   Anthropic : export ANTHROPIC_API_KEY=sk-ant-...
#   OpenAI    : export OPENAI_API_KEY=sk-...
#   Gemini    : export GOOGLE_API_KEY=AI...

AI_PROVIDER = "anthropic"          # "anthropic"  |  "openai"  |  "gemini"

AI_MODEL = {
    "anthropic" : "claude-sonnet-4-6",
    "openai"    : "gpt-4o",
    "gemini"    : "gemini-1.5-pro",
}[AI_PROVIDER]
