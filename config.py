"""
GeoSense — config.py
---------------------
All user-facing settings live here.
Change AI_PROVIDER and thresholds as needed.
Nothing else in the project needs to be edited for normal use.

Excel file is resolved relative to this file's own location:
    GeoSense/
    └── data/
        └── POLICE_STATION.xlsx
Place your Excel file there and it will be picked up automatically,
regardless of which directory you run the script from.
"""

from pathlib import Path

# ── Excel Source ───────────────────────────────────────────────────────────────
EXCEL_FILE   = Path(__file__).parent / "data" / "POLICE_STATION.xlsx"
SHEET_NAME   = "PoliceStation"
COL_DISTRICT = "DISTRICT"
COL_PS       = "POLICE STATION"

# ── Matching Thresholds ────────────────────────────────────────────────────────
FUZZY_CUTOFF    = 80    # 0–100: scores below this are rejected
LOCALITY_CUTOFF = 86    # stricter cutoff for address-locality → PS/District scans
TOP_N           = 3     # number of results to return

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
