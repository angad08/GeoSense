# GeoSense Architecture

## Overview

GeoSense is a two-tier system: a **shared core** (`common/`) that handles data loading, text matching, and I/O, plus **two independent ranking engines** (`v1/`, `v2/`) that implement different algorithms.

## Core Layers

### 1. Data Layer (`common/loader.py`)
- Loads the `PoliceStation` sheet into a clean pandas DataFrame
- Strips and uppercases values, drops null rows
- **Output**: `DataFrame(columns=['DISTRICT', 'POLICE STATION'])`
- Station coordinates (`LAT`/`LNG` columns) are read separately by
  `v2/geopy_distance.py` with openpyxl, so writes never disturb other sheets

### 2. Text Matching Layer (`common/matcher.py`)
- **Fuzzy matching** (lenient): RapidFuzz scoring for names the user *typed*
  (threshold: `FUZZY_CUTOFF = 80`)
- **Locality scanning** (strict): reads locality names out of a free-text
  address and matches them against known stations and districts. Strict
  scoring rules stop junk tokens (door numbers, generic words like "NAGAR")
  from ever producing a false match — a wrong answer is worse than no answer
- **Returns**: ranked matches with scores, or empty so the query falls
  through to the next rung

### 3. Ranking Engines (`v1/engine.py`, `v2/engine.py`)
Execute in order:
1. Try fuzzy name match → return if found (high confidence)
2. Try locality scan → return if found (medium confidence)  
3. Fall back to ranking algorithm:
   - **v1**: Call AI, estimate distances, rank
   - **v2**: Geocode address, calculate real distances, rank

### 4. Output Layer (`common/output.py`)
- Formats results as a table (tabulate)
- Maps internal confidence to plain-English surety labels:
  Guaranteed / Very Likely / Likely / Possible / Unknown
- Prints the advisory warning the engine attached (v2 Case 2 distance check)

### 5. Logging Layer (`common/lookup_log.py`)
- Appends each lookup to the `LookupResults` sheet in the same workbook
- Columns: `ADDRESS | RESULT LOOKUP | RESULT MATCH` — the logged wording
  always matches what was displayed to the user

## Ranking Engines in Detail

### v1: AI-Based Ranking

```
Input: (address, district, optional) → common/loader loads Excel

Step 1: Text Match
  └─ Try fuzzy station name match
  └─ Try locality address scan
  └─ Return if found

Step 2: AI Ranking (v1/ai_engine.py)
  ├─ Call AI to estimate distance for each station in district
  ├─ AI also infers district if missing
  └─ Rank by AI-estimated distance (ascending)

Step 3: Format & Log
  └─ Output top 3 with confidence labels
  └─ Append to LookupResults sheet
```

**The guarantee that matters:** the AI is constrained to choose only from the
station list supplied from the Excel, and every name it returns is validated
against the Excel again — anything not in your data is discarded. The result:
**zero invented stations**, ever.

**Tradeoff**: 
- ✓ Works with no Google Maps key
- ✓ Infers missing districts from address text
- ✗ Distances are estimates, not measurements
- ✗ API latency and token cost on every ranked lookup

### v2: Geodesic Distance (AI only as last resort)

```
Input: (address, district, optional) → common/loader loads Excel

Step 1: Text Match (same as v1)
  └─ Return if fuzzy or locality match found — no API call at all

Step 2: AI District Inference (v2/ai_engine.py) — ONLY if text matching failed
  └─ AI infers the district from the address text (Excel list only,
     no invented names) — this is v2's single AI job

Step 3: Distance Ranking (v2/geopy_distance.py)
  ├─ Station coords read from the Excel's LAT/LNG columns (geocoded once,
  │  on demand, and written back — no rebuild step)
  ├─ Google Maps Geocoding API: input address → (lat, lng) — the 1 live call
  ├─ WGS-84 geodesic distance to each station, rank ascending
  └─ If the input address will not geocode → the district's stations are
     returned UNRANKED with low confidence, stated in the method string —
     never a silent empty result

Step 4: Format & Log
  └─ Output top 3 with measured distances
  └─ Advisory warning if the nearest station is farther than
     DISTANCE_WARN_KM (default: 30) — the stated district may be wrong
  └─ Append to LookupResults sheet
```

**Tradeoff**:
- ✓ Precise real distances (WGS-84, Karney's algorithm)
- ✓ One geocode per station ever; one API call per warm lookup
- ✓ AI touched only when the Excel text scan can't answer
- ✗ Needs a Google Maps API key for the distance rung
- ✗ First lookup in a cold district geocodes that district's stations once

## Module Dependencies

```
main.py (version router)
  ├─ v1/app.py
  │   ├─ common/cli.py (shared arg parsing + loop)
  │   ├─ v1/engine.py (fuzzy → locality → AI rank)
  │   │   ├─ common/matcher.py
  │   │   ├─ common/loader.py
  │   │   ├─ v1/ai_engine.py
  │   │   └─ common/ai_client.py
  │   └─ common/output.py + common/lookup_log.py
  │
  └─ v2/app.py
      ├─ common/cli.py (shared arg parsing + loop)
      ├─ v2/engine.py (fuzzy → locality → geodesic rank)
      │   ├─ common/matcher.py
      │   ├─ common/loader.py
      │   ├─ v2/geopy_distance.py (geocoding + distance)
      │   └─ v2/ai_engine.py (AI inference fallback)
      │       └─ common/ai_client.py
      └─ common/output.py + common/lookup_log.py

common/api_keys.py (env vars + optional .env; validated lazily, at first real use)
common/config.py (shared settings)
  ↑
v2/config.py (extends common/config.py with DISTANCE_WARN_KM)
```

## Key Design Decisions

### Why `common/cli.py` exists
- Both v1 and v2 need interactive + one-shot modes
- Identical argument parsing in both
- Shared logic → `common/cli.py`
- Each `app.py` wires CLI to its engine

### Why v2 has its own `config.py`
- `DISTANCE_WARN_KM` is v2-specific
- Instead of conditional logic in `common/config.py`, v2 imports base and extends
- v1 uses `common/config.py` directly
- **Rule**: If a setting is only one version uses it, put it in that version's config

### Why text matching runs before ranking
- Any lookup the fuzzy or locality rung can answer costs zero API calls
- API calls (AI/geocoding) are the fallback for addresses the Excel text
  can't resolve directly
- Each rung only executes if the one before it could not answer

### Why logging happens after output
- Output → confidence labels and warnings already decided
- Log records what was displayed (audit trail)
- If output format changes, log format changes in parallel

## Data Flow Examples (real lookups against the Telangana dataset)

### Case 1 — station known (no API call)
```
Input: --ps "Gachibowli"
    ↓
Fuzzy Match: exact match (score 100) on GACHIBOWLI ✓
    ↓
Output: GACHIBOWLI | CYBERABAD-RANGAREDDY | Guaranteed
    ↓
Log: appended to LookupResults
```

### Case 3a — address names a station area (no API call)
```
Input: --address "6-31-1, Akhila Enclave, Old Bowenpally, Secunderabad, 500011"
    ↓
Fuzzy Match: not applicable (no station name typed)
    ↓
Locality Scan: token "BOWENPALLY" → BOWENPALLY PS ✓
    ↓
Output: BOWENPALLY | MALKAJGIRI-HYDERABAD | Very Likely
    ↓
Log: appended to LookupResults
```

### Case 2 — district known, address ranked by distance (1 API call when warm)
```
Input: --district "Malkajgiri-Rangareddy" --address "<full address>"
    ↓
Fuzzy Match district: MALKAJGIRI-RANGAREDDY (100%)
    ↓
Text-first pin: if the address itself names a station in that district,
                it is pinned at rank 1
    ↓
Geocode input address (1 API call) → geodesic distance to each station's
cached coordinates → rank ascending
    ↓
Output: top 3 with measured distances; advisory warning if the nearest
        station is > DISTANCE_WARN_KM (30 km) away
    ↓
Log: appended to LookupResults
```

## Testing Strategy

### Regression Tests (`tests/validate_test_cases.py`)
A 9-check harness that needs **no API keys and makes no network calls** —
the paid rungs (AI, geocoding) are mocked out:
- **#1–#7**: real messy addresses, address-only. v1 and v2 must return the
  same rank-1 station, matching a recorded baseline. (#3 is a deliberately
  recorded known failure — it names BALANAGAR where SANATHNAGAR is expected.)
- **#8**: a negative case — an address with no usable signal must return
  *nothing* rather than a lucky junk-token guess.
- **#9**: v2's Case-2 text-first pin — a station named in the address text
  must stay pinned at rank 1 above the distance ranking.

### Running Tests
```bash
python -m tests.validate_test_cases
```
Expected last line: `... => ALL GREEN`

## Performance Characteristics

| Operation | Cost | Notes |
|-----------|------|-------|
| Fuzzy match | Free, in-memory | RapidFuzz over the loaded DataFrame |
| Locality scan | Free, in-memory | Token extraction + strict scoring |
| Distance ranking (v2, warm) | 1 geocode API call | Station coords come from the Excel |
| Distance ranking (v2, cold district) | 1 call per uncached station, once ever | Written back to the Excel |
| AI rung | 1 model call | Only when text matching can't answer |

## Future Extensions

### v3: Machine Learning Ranking
- Train on historical lookup patterns
- Rank without AI/geocoding API calls
- Zero latency, minimal cost

### Input-Address Caching
- Station coordinates are already cached in the Excel (done)
- A small cache for repeat *input* addresses could remove the last
  API call for frequently looked-up addresses

### Confidence Scoring
- Track lookup accuracy vs. user feedback
- Adjust confidence thresholds dynamically
