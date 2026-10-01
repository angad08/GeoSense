# GeoSense — Independent Review Brief (for Codex)

**Date:** 2026-10-01 · **Written by:** Claude Code, handing off for a second opinion
**Decision owner:** the project owner. You evaluate and propose; they decide.

---

## 0. What we want from you

1. **Evaluate all of GeoSense.** That means the code, the data, the approach, and the changes made on 2026-09-30 and 2026-10-01 (§5). Don't just re-check our conclusions. Tell us if something is wrong, fragile, or over-built.
2. **Answer the core question:** *Is GeoSense fit for live use on real passport-verification addresses in Telangana, Andhra Pradesh and Tamil Nadu? If not, what exactly stands in the way?*
3. **Propose fixes for the open issues in §6**, the stacked-coordinates issue (§6.1) above all. For each proposal give the approach, the expected effect, its cost (API calls and money), the risk, and how to verify it.
4. **Deliver a written report.** Put it in `CODEX_REVIEW.md` at the project root, ranked by severity, with evidence (file:line, command output, counts).

### Ground rules (hard constraints from the owner)
- **Do NOT modify code or data.** This is evaluation only. The owner decides afterwards what gets built.
- **Never delete, merge, dedupe or rename rows in `data/POLICE_STATION.xlsx`.** The station list comes from GPSP exactly as-is, including rows that look outdated or duplicated. The only columns the code ever writes are `LAT`/`LNG` (plus the `LookupLogs` sheet).
- **Nothing may be hardcoded to a region.** No state lists, per-state boxes, or Telangana-specific rules. Any Indian state added to the sheet must work with no code or config change. Everything state-related must come from the data (the `STATE` column) or from Google's response.
- **Google API calls cost money.** Read-only local analysis is free, and so is `--dry-run`. If you need live calls, keep them to a small sample (≤ 20) and say how many you made. `GOOGLE_MAPS_API_KEY` is set in the environment.
- **Keep the Excel closed while any script runs.** Writes fail if it's open.

---

## 1. What GeoSense is

**Problem:** passport-verification application forms have free-text addresses. Each has to be assigned the correct **police station (PS)** for verification. The reference list is a sheet of police stations. The address has no PS field, and nothing consistently links the two.

**Input per lookup:** an address (free text, messy), optionally a known PS name and/or a known district.
**Output:** the top 3 candidate stations, always real rows from the sheet (never invented), each with a confidence label, the method used, and the state scope searched.

**Domain reality:** addresses look like
`"7-8-237 GOUTHAM NAGAR , FEROZGUDA,BALANAGAR,telangana, pin 500011"`. They mix door numbers, colonies, landmarks, localities, district, state and PIN in any order and any spelling.

---

## 2. Code map

```
main.py                     entry point
common/
  config.py                 all settings (paths, columns, cutoffs, sanity-check constants)
  loader.py                 loads PoliceStation sheet → DataFrame(DISTRICT, POLICE STATION, STATE, ...)
  state_filter.py           detects the state named in the address (from STATE column), narrows df;
                            region_phrase()/district_list_text() for AI prompts
  matcher.py                fuzzy name matching (typed names) + strict locality scan of addresses;
                            4 documented invariants (I1–I4) against junk-token matches;
                            state_stopwords(df): state words ignored as localities (data-driven)
  ai_client.py              provider-agnostic AI client (anthropic | openai | gemini)
  output.py, cli.py         table output, confidence labels, CLI
  lookup_log.py             appends each lookup to the LookupLogs sheet
v1/  engine.py, ai_engine.py    ladder: fuzzy → locality → AI ranks stations (AI-estimated distance)
v2/  engine.py, ai_engine.py    ladder: fuzzy → locality → geocode + real geodesic distance → AI last
     geopy_distance.py          geocoding, station coordinates stored in the Excel, all geocode sanity checks
scripts/build_ps_coords.py  bulk-fills LAT/LNG; --dry-run, --limit N, --audit [--fix]
tests/validate_test_cases.py  regression suite (22 checks)
```

Read `ARCHITECTURE.md` and `README.md` for the full design. `v2/engine.py`'s module docstring gives the exact case ladder:

- **Case 1** (known PS): fuzzy match against the sheet.
- **Case 2** (known district): filter to the district, geocode the address, rank by real distance.
- **Case 3a** (address names a PS): text match, then a distance check.
- **Case 3b** (address names a district): geocode and rank.
- **Case 3n** (no state named): nearest stations across all states.
- **Case 3c** (address unmatched): AI infers the district, then geocode and rank.
- **Case 0**: nothing matched; return an empty result.

State filtering runs before every case.

---

## 3. Data

`data/POLICE_STATION.xlsx`
- Sheet **`PoliceStation`** has columns `DISTRICT`, `POLICE STATION`, `LAT`, `LNG`, `STATE`, with 3,000 rows:

  | State | Rows | With LAT/LNG |
  |---|---|---|
  | Andhra Pradesh | 870 | 869 |
  | Tamil Nadu | 1,379 | 1,368 |
  | Telangana | 751 | 749 |

- Sheet **`LookupLogs`** holds 27 real lookups logged so far. The owner-maintained columns `ACTUAL PS KNOWN` and `MATCH` are **empty for all 27**, so **no real-world accuracy has been measured.**
- Backups (do not modify) are in `data/`:
  - `POLICE_STATION.backup-2026-09-30-before-AP-geocode.xlsx`
  - `POLICE_STATION.backup-2026-10-01-before-TN-geocode.xlsx`
  - `POLICE_STATION.backup-2026-10-01-after-TN-fill.xlsx`

**Data quirks, all real and all to be handled in code, not by editing rows:**
- **Station codes in names:** Chennai, Tambaram, Avadi and Madurai city stations carry codes: `K-4 ANNANAGAR`, `T16 SAMMANCHERIR`, `D3-KOODAL PUDUR`, `E3-ANNA .NAGAR.`.
- **Suffixes and abbreviations:** `BHAVANI P.S`, `LAKE PS`, `AWPS ARUPPUKOTTAI` (All Women PS), `U/G`, parentheticals like `VENKATAPUR (MULUGU)` and `RAIPOL (BEGAMPET)`.
- **Police districts are not revenue districts:** commissionerates like `CYBERABAD-MEDCHAL`, `AVADI`, `TAMBARAM` and `FUTURE CITY-RANGA REDDY`; Google uses revenue districts.
- **Stale district boundaries:** Tamil Nadu split Vellore into Vellore, Ranipet and Tirupathur in 2019, but about 25 stations appear under both `VELLORE` and their new district. AP redrew its districts in 2022 (Bapatla from Prakasam, Annamayya from Chittoor/YSR), and some rows reflect the older grouping.
- **Repeated names:** the same station name exists in different districts and states (NAWABPET, GUDUR, KEERANUR, BALANAGAR, ALANGULAM…).
- **Misspellings:** e.g. `NADUIVATTEM`, probably Naduvattam.

---

## 4. How station coordinates are produced (current design)

Coordinates are geocoded **once per station** and stored in `LAT`/`LNG`. The Excel is the only store; there's no separate cache file. A blank cell means "not yet geocoded", and it gets retried on the next run or lookup.

Query: `"{clean PS name} Police Station, {DISTRICT}, {STATE}, India"`, using Google Geocoding with `components={"country": "IN"}` and `language="en"`.

- `clean_station_name()` strips station codes, PS suffixes and stray dots, and keeps initials (`P.N.PALAYAM`).
- A row with a blank STATE is skipped, never defaulted.

**Checks in `v2/geopy_distance.py::geocode_station()`, in order.** Any failure leaves the cell blank with a named warning:

1. **Inside India's outer box**: lat 6.0–37.6, lng 68.0–97.5 (`COORD_*`).
2. **Not a vague area result**: reject types `country` and `administrative_area_level_1/2/3`. Those mean Google found only a state, district or taluk centre, not the station.
3. **Same state as the row**: Google's `administrative_area_level_1` is fuzzy-matched (token-set) to the row's STATE. If Google gives the name in local script (e.g. `தமிழ் நாடு`), the point is reverse-geocoded in English first (`_english_state_at`).
4. **Not a same-name place elsewhere (sibling rule)**: reject only if BOTH conditions hold:
   - (a) the point is more than `SIBLING_MAX_KM = 35` km from every other stored station of the same sheet district (judged only when the district has at least `SIBLING_MIN_COUNT = 3` stored stations), AND
   - (b) Google's district (`administrative_area_level_3`, else `level_2`) doesn't match the row's DISTRICT (`same_district()`, which is lenient on spacing and spelling).

   Calibration measured on about 3,000 stations: the median distance to the nearest sibling is 6.0 km, p95 is 15.8 km and p99 is 21.4 km; the wrong results were 41–251 km out.
   - Sibling distance alone falsely flagged remote-but-correct stations (EAGALAPENTA by the Srisailam dam, YATAPAKA, DOWLTABAD, MATTAMPALLY).
   - District name alone falsely flagged about 40 correct stations across redrawn boundaries.
   - Together, on the stored data, they flagged exactly the 7 known-wrong stations and none of the correct ones.

`scripts/build_ps_coords.py` re-checks the whole new batch against the sibling rule before saving, because a brand-new district has no stored siblings while the loop runs. `--audit` re-checks stored coordinates, and `--audit --fix` clears the suspects.

---

## 5. What changed on 2026-09-30 → 2026-10-01 (please scrutinise)

1. **Removed a hardcoded Telangana+AP bounding box** (lat 12.5–20, lng 76.5–85). It had silently rejected 1,055 Tamil Nadu stations, everything south of 12.5°N. It was replaced by checks 1 and 3 above.
2. **Made everything state-agnostic:**
   - matcher stopwords are now built from the STATE column (`state_stopwords`), except a state word that is also part of a real station name (e.g. `TAMIL` because of `TAMIL UNIVERSITY`);
   - the v1 and v2 AI prompts name the states actually being searched (`region_phrase`) and group districts by state.
3. **Added station-name cleaning, the vague-result check, the English/local-script fix, and the sibling rule** (checks 2–4).
4. **Filled 1,047 Tamil Nadu coordinates**, plus S.S.KOTTAI after the script fix, all from a trial of 12 first.
5. **Audited existing coordinates** and cleared 7 wrong ones: GUDUR (Kurnool) had been placed at the Gudur in Tirupati district, 251 km off; BALANAGAR (Mahabubnagar) and RAIPOL (BEGAMPET) (Siddipet) had landed in Hyderabad; KOVILPALAYAM, T T PETTAI, ANNAIKATTU and KEERANUR had matched same-name places elsewhere.
6. **Bugs found and fixed along the way:**
   - Google returned state names in Tamil script;
   - openpyxl's `ws.cell(..., value=None)` silently doesn't clear a cell, so "cleared" had been reported falsely until it was changed to `.value = None`.
7. The test suite passes throughout (`ALL GREEN`), **but it contains only Telangana cases** (see §6.5).

---

## 6. Open issues, for you to evaluate and propose on

### 6.1 Stacked coordinates (top priority)
**395 stations (about 13%) share an identical coordinate with a *differently named* station**, across 130 points in all three states (AP 116 rows, TN 193, TS 122 rows on shared points, counting all duplicates). The largest clusters:
- 18 stations in MADURAI RURAL on one point;
- 11 in RAMAGUNDAM-MANCHERIAL/PEDDAPALLI;
- 9 in TIRUNELVELI CITY/RURAL;
- 8 each in NALGONDA and SRIKAKULAM;
- 7 each in WARANGAL, NAGARKURNOOL and JAGITYAL.

**Likely cause:** when Google can't find a small station, it returns one nearby police POI (probably the district SP office or a big town station) for all of them. These results pass every check: right state, right district, and near siblings, because the siblings are the stack itself. The consequence is that v2's nearest-station ranking can't separate those stations.
**Some sharing is legitimate:** an All Women PS co-located with the town station, the same station listed under an old and a new district (Vellore/Ranipet/Tirupathur), and spelling variants (`AVANIAPURAM` / `AVANIYAPURAM`).

**Idea under consideration (not built):** treat "the point is already used by a differently named station" as a failure. Retry with the **Google Places API** (Text Search / Find Place), which returns the matched place's *name*, and fuzzy-verify that name against the station. This is a different API (it may need enabling on the key and has different pricing), and would cost roughly 400 calls.

Please:
- evaluate this idea against alternatives;
- estimate how many of the 395 are genuinely wrong;
- say how to separate legitimate co-location;
- say how the rule should apply at fill time, including for a brand-new state.

Reproduce the count with:
```python
import pandas as pd, re
df = pd.read_excel('data/POLICE_STATION.xlsx').dropna(subset=['LAT'])
k = lambda s: re.sub(r'[^A-Z]', '', s.upper())
stacked = [x for _, x in df.groupby(['LAT', 'LNG']) if len({k(n) for n in x['POLICE STATION']}) > 1]
print(sum(len(x) for x in stacked), 'stations on', len(stacked), 'shared points')
```

### 6.2 Fourteen stations deliberately left blank
Each was rejected by a check, and the warnings say why. They need a name fix, or hand-entered coordinates, which are never overwritten.
- **Only an area centre found:** BAZAAR (Ramanathapuram), NADUIVATTEM and TOWN CENTRAL (Nilgiris), ETHAKOIL (Theni), PERUGAVALTHAN (Thiruvarur), CHENAM (Tiruvannamalai).
- **Same-name place elsewhere:** GUDUR (Kurnool), KOVILPALAYAM (Ramanathapuram), T T PETTAI (Trichy Rural), ANNAIKATTU (Chengalpattu), KEERANUR (Dindigul), BALANAGAR (Mahabubnagar), RAIPOL (BEGAMPET) (Siddipet).
- **Wrong state:** T.V.NALLUR (Viluppuram) was placed in Puducherry.

Since rows can't be edited, is there a better code-side approach? Consider Places, biasing the search to the sibling-station area, or treating the parenthetical in `RAIPOL (BEGAMPET)` differently.

### 6.3 Text matching of Tamil Nadu-style names
The address text `ANNA NAGAR` doesn't match the station `K-4 ANNANAGAR`. The causes are the codes, joined versus split words, and stray punctuation. `common/matcher.py` was built around Telangana-style names.
- v2 falls back to distance, which depends on §6.1.
- v1 has no fallback, so it just misses.

Evaluate the matcher's invariants (I1–I4) against TN and AP naming.

### 6.4 Duplicate station rows across districts
About 25 stations appear under both `VELLORE` and `RANIPET`/`TIRUPATHUR`, and similar cases exist elsewhere. A lookup may return both, or only the older district. The rows stay (see the ground rules), so how should results present or rank them?

### 6.5 Tests and accuracy measurement
- `tests/validate_test_cases.py` has Telangana cases only. There's no coverage for TN/AP addresses, `clean_station_name`, `same_state`/`same_district`, the sibling rule, the vague-result check or the audit.
- There's no measured live accuracy (LookupLogs MATCH is empty).

Propose a test set and a measurement plan: for example, officers fill `ACTUAL PS KNOWN`/`MATCH` during a shadow run, targeting about 100 lookups per state.

### 6.6 Anything else you find
Examples: correctness, robustness, cost per lookup, latency, failure modes when Google or the AI is down, config sprawl, and v1 vs v2 (should both be kept?).

### 6.7 Housekeeping
The folder is **not a git repository**, so there's no version history. Only the Excel backups exist.

---

## 7. How to run things

Run from the project root, with the Excel closed:

```bash
python tests/validate_test_cases.py              # regression suite, expect "ALL GREEN"
python scripts/build_ps_coords.py --dry-run      # queries for blank stations; no API calls, no writes
python scripts/build_ps_coords.py --audit        # re-check stored coords (API calls only for isolated ones); report only
python v2/app.py --address "..." [--ps ...] [--district ...]   # one lookup (geocoding = paid, AI rung = paid)
python v1/app.py --address "..."
```

Useful free, local analyses: nearest-sibling distances per district, the shared-coordinate clusters (§6.1), and name-format surveys of the `POLICE STATION` column.

---

## 8. Our current verdict (challenge it)

**Usable live only as an assistant that suggests stations for an officer to confirm, not for automatic decisions.**
- It never invents a station, and it scopes searches to the right state.
- Typed PS or district lookups are reliable.
- Telangana address lookups were tested (rank-1 correct in 6 of 7 cases).
- TN and AP address-only lookups are **unmeasured**, and §6.1 makes about 13% of stations unreliable in v2 distance ranking.

We'd fix §6.1 before relying on TN/AP address-only lookups, then measure accuracy through a shadow run.

Tell us where this verdict is wrong.
