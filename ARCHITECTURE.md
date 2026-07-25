# GeoSense Architecture

## Overview

GeoSense is a two-tier system: a **shared core** (`common/`) that handles data loading, text matching, and I/O, plus **two independent ranking engines** (`v1/`, `v2/`) that implement different algorithms.

## Core Layers

### 1. Data Layer (`common/loader.py`)
- Loads Excel file into a clean pandas DataFrame
- Normalizes station names, districts, localities
- Handles missing/corrupted values gracefully
- **Output**: `DataFrame(columns=['station', 'district', 'locality', 'coords', ...])`

### 2. Text Matching Layer (`common/matcher.py`)
- **Fuzzy matching**: Uses RapidFuzz to find station name matches (threshold: 80%)
- **Locality scanning**: Maps address text to known localities, returns matching stations
- **Returns**: `(matched_stations, confidence_score)` or empty if no match

### 3. Ranking Engines (`v1/engine.py`, `v2/engine.py`)
Execute in order:
1. Try fuzzy name match → return if found (high confidence)
2. Try locality scan → return if found (medium confidence)  
3. Fall back to ranking algorithm:
   - **v1**: Call AI, estimate distances, rank
   - **v2**: Geocode address, calculate real distances, rank

### 4. Output Layer (`common/output.py`)
- Formats results as a table (tabulate)
- Attaches confidence labels: High/Medium/Low
- Adds distance warnings if v2 distance > threshold

### 5. Logging Layer (`common/lookup_log.py`)
- Appends each lookup to `LookupResults` sheet in Excel
- Records: `(address, district, matched_station, confidence, timestamp)`

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

**AI Prompt Pattern**:
```
You are a geography expert. For a person at "<address>" needing the 
closest police station in "<district>", rank these stations by distance:
[station list]

Return JSON: {"stations": [{"name": "...", "distance_km": N, "reason": "..."}]}
```

**Tradeoff**: 
- ✓ Understands context ("near the mall" → searches that area)
- ✓ Infers missing districts from address text
- ✗ 1-3 second API latency per lookup
- ✗ Costs API tokens

### v2: Geodesic Distance + AI Fallback

```
Input: (address, district, optional) → common/loader loads Excel

Step 1: Text Match (same as v1)
  └─ Return if fuzzy or locality match found

Step 2: Geocoding (v2/geopy_distance.py)
  ├─ Google Maps API: Convert address → (lat, lon)
  ├─ Calculate WGS-84 geodesic distance to each station
  └─ Rank by distance (ascending)

Step 3: AI Fallback (v2/ai_engine.py)
  └─ If address doesn't geocode → call AI to infer district only
  └─ Return stations in that district (no distance ranking)

Step 4: Format & Log
  └─ Output top 3 with distances
  └─ Add warning if distance > DISTANCE_WARN_KM (default: 15)
  └─ Append to LookupResults sheet
```

**Tradeoff**:
- ✓ <500ms latency (geocoding cache)
- ✓ Precise real distances (WGS-84)
- ✓ Lower API cost (geocoding cheaper than ranking)
- ✗ Requires valid addresses (unrecognized → AI fallback)
- ✗ Needs Google Maps API key

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

common/api_keys.py (read all keys once, before first use)
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
- Fuzzy + locality cover ~95% of lookups with zero API cost
- API calls (AI/geocoding) are fallback for unusual addresses
- Ranking tier only executes when needed

### Why logging happens after output
- Output → confidence labels and warnings already decided
- Log records what was displayed (audit trail)
- If output format changes, log format changes in parallel

## Data Flow Example: "Find PS for Madhapur, Rangareddy"

### v1 Flow
```
Input: address="Madhapur", district="Rangareddy"
    ↓
Fuzzy Match: "Madhapur" → 95% match with "Madhapur PS" ✓
    ↓
Output: {station: "Madhapur PS", district: "Rangareddy", confidence: "High"}
    ↓
Log: "Madhapur" → "Madhapur PS" (fuzzy)
```

### v2 Flow
```
Input: address="100ft Road near Phoenix Park, Madhapur"
    ↓
Fuzzy Match: No 95%+ match ✗
    ↓
Locality Scan: "Madhapur" → "Madhapur PS", "Gachibowli PS" ✓
    ↓
Output: Top 2 stations by locality match
    ↓
Log: Address → Top matches (locality)
```

### v2 with Ranking
```
Input: address="Near CMH Hospital", district="Rangareddy"
    ↓
Fuzzy Match: No match ✗
    ↓
Locality Scan: No match ✗
    ↓
Geocode: "CMH Hospital, Rangareddy" → (lat=17.xxx, lon=78.xxx)
    ↓
Distance Calc: {Madhapur PS: 2.3km, Gachibowli PS: 4.1km, ...}
    ↓
Rank & Output: Top 3 by distance with warnings if >15km
    ↓
Log: Address → Top 3 (geodesic)
```

## Testing Strategy

### Regression Tests (`tests/validate_test_cases.py`)
- No network calls (mocked API responses)
- Covers:
  - Fuzzy matching edge cases
  - Locality scanning with special characters
  - Ranking logic (order of results)
  - Output formatting

### Running Tests
```bash
python -m tests.validate_test_cases
```

## Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| Fuzzy match | <5ms | In-memory, RapidFuzz |
| Locality scan | <10ms | Pandas string search |
| Geocoding (v2) | 200-500ms | Google Maps API, cached |
| AI ranking (v1) | 1-3s | Anthropic API |
| Full lookup (cached) | <10ms | If text match succeeds |
| Full lookup (AI/geocode) | 1-3s | First time only |

## Future Extensions

### v3: Machine Learning Ranking
- Train on historical lookup patterns
- Rank without AI/geocoding API calls
- Zero latency, minimal cost

### Caching Layer
- Redis/local cache for geocoding results
- 99% hit rate for repeat addresses
- Reduces API calls by 10x

### Confidence Scoring
- Track lookup accuracy vs. user feedback
- Adjust confidence thresholds dynamically
