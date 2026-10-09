"""
GeoSense — v2/config.py  (per-version, imports the shared base)
----------------------------------------------------------------
V2 needs one value V1 does not: DISTANCE_WARN_KM (the Case-2 geodesic sanity
check). Everything else is the shared base, re-exported from common.config so
that every v2 module imports its settings from a single namespace (v2.config).

API keys are read from environment variables — see common/api_keys.py.
    Required always  : GOOGLE_MAPS_API_KEY
    Required for AI  : ANTHROPIC_API_KEY | OPENAI_API_KEY | GOOGLE_API_KEY
"""

# Re-export the shared base explicitly (clear for linters; no wildcard magic).
from common.config import (
    PROJECT_ROOT, EXCEL_FILE, SHEET_NAME, COL_DISTRICT, COL_PS, COL_STATE,
    FUZZY_CUTOFF, LOCALITY_CUTOFF, TOP_N, MIN_LOCALITY_LEN, MAX_TIE_WIDTH,
    LOG_SHEET_NAME, LOG_WRITE_COLS, LOG_MANUAL_COLS, AI_PROVIDER, AI_MODEL,
    COL_LAT, COL_LNG, GEOCODE_COUNTRY, STATE_MATCH_CUTOFF, SEARCH_ALIAS_FILE,
    SIBLING_MAX_KM, SIBLING_MIN_COUNT, STATION_PLACE_MATCH,
    COORD_LAT_MIN, COORD_LAT_MAX, COORD_LNG_MIN, COORD_LNG_MAX,
)

# ── Distance Sanity Check (v2 only) ────────────────────────────────────────────
DISTANCE_WARN_KM = 30   # Case 2: if nearest PS in the stated district is farther
                        # than this, flag that the stated district may be wrong

# ── Cross-district neighbour check (v2 only) ──────────────────────────────────
# Case 2 filters to the stated district, so a station just over the boundary is
# dropped before distance is ever computed — even when it is far nearer. After
# ranking the district, the scope is scanned again across all districts and any
# clearly nearer neighbour is surfaced alongside, for the human to judge.
#
# The margin keeps it signal, not noise: a neighbour 0.1 km nearer changes
# nothing, so only one nearer by this much is worth showing.
CROSS_DISTRICT_MARGIN_KM = 1.0
CROSS_DISTRICT_MAX       = 2    # at most this many neighbours, nearest first

# Hard ceiling on the whole table. Normal lookups stay at TOP_N (3); a genuinely
# nearer station outside the district may push past that, but the list must stay
# short enough to compare at a glance. Enforced on the final list rather than
# left to TOP_N + CROSS_DISTRICT_MAX happening to add up, so raising either one
# cannot quietly produce a longer table. Neighbours lead the list, so trimming
# takes from the far end of the district's own ranking.
MAX_RESULTS = 5
