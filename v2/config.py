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
    PROJECT_ROOT, EXCEL_FILE, SHEET_NAME, COL_DISTRICT, COL_PS,
    FUZZY_CUTOFF, LOCALITY_CUTOFF, TOP_N, MIN_LOCALITY_LEN, MAX_TIE_WIDTH,
    LOG_SHEET_NAME, LOG_WRITE_COLS, LOG_MANUAL_COLS, AI_PROVIDER, AI_MODEL,
    GEOCODE_SUFFIX, COL_LAT, COL_LNG,
)

# ── Distance Sanity Check (v2 only) ────────────────────────────────────────────
DISTANCE_WARN_KM = 30   # Case 2: if nearest PS in the stated district is farther
                        # than this, flag that the stated district may be wrong
