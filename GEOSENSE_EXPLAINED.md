# GeoSense — What It Is and How It Works

**For:** Codex, taking over the project · **Written by:** Claude Code (original builder) · **As of:** 2026-10-01, after the original ladder was restored (git commit after `bdb9634`)
**Companion docs:** `CODEX_BRIEF.md` (open issues and constraints), `CODEX_REVIEW.md` (your review), `README.md`, `ARCHITECTURE.md`

---

## 1. The job, in the owner's words

Passport verification in India needs each applicant assigned to a **police station (PS)** that will do the verification. The applicant writes an address on the form and often picks a station themselves. **That pick is frequently a guess.** Many applicants live abroad (for example in Australia), choose a name that *sounds* local, and are wrong.

**GeoSense takes the address and shows the 3 nearest real police stations, with distances.** The officer picks from those, normally the nearest.

**There is no single "right answer".** When several stations are close, any of them is acceptable. So:
- success means **the stations shown really are the nearest ones and the distances are true**, not that GeoSense reproduced one particular name;
- the applicant's guessed station or district is a **hint, not ground truth**;
- **distance quality is the product.** Wrong or stacked station coordinates (CODEX_BRIEF §6.1) hurt the core output directly, not as a side issue.

**Users:** verification officers, one address at a time, from a command line. They read a small table and choose.

---

## 2. Inputs and outputs

**Input per lookup:**
- `address`: free text, messy. Example: `"7-8-237 GOUTHAM NAGAR , FEROZGUDA,BALANAGAR,telangana, pin 500011"`. Door numbers, colonies, landmarks, locality, district, state and PIN come in any order, spelling and case.
- `ps` (optional): the station the applicant typed, possibly a guess.
- `district` (optional): the district the applicant typed, possibly a guess.

**Output:** a table of up to 3 rows: rank, police station, district, a Confidence label, and distance. A State column is added only when every state was searched (no station, district or state to go on). Under the table go the state line (only when a state was named or every state was searched), plus any warning or note.

```
#  Police Station   District        Confidence     Distance
1  BORABANDA        HYDERABAD       Very Likely    ~1.2 km
2  SR NAGAR         HYDERABAD       Likely         ~2.9 km
3  ...
  Compare the nearby candidates and their distances before selecting.
  State: TELANGANA (named in address) — only TELANGANA stations searched
  [!] warning text if something looks off
```

**Hard guarantee: every station shown is a real row from the sheet.** Nothing is invented, not even by the AI. Any name the AI returns is re-validated against the sheet.

The Confidence labels (`common/output.py`, column headed "Confidence" since 2026-10-01) are **Guaranteed / Very Likely / Likely / Possible / Unknown**. They map from internal confidence levels VERY HIGH / HIGH / MEDIUM / LOW / NONE, and the same words are written to `LookupLogs` → `RESULT MATCH`. Codex briefly renamed them; they were restored so new log rows stay consistent with the existing ones. If they're ever changed, change both together and keep the log readable.

---

## 3. The data

**`data/POLICE_STATION.xlsx` is fetched from GPSP as-is. Never delete, dedupe, merge or rename rows.** Messy source data is handled in code. The code writes only `LAT`/`LNG` and the `LookupLogs` sheet.

**Sheet `PoliceStation`** has columns `DISTRICT`, `POLICE STATION`, `LAT`, `LNG`, `STATE`, with 3,000 rows: TS 751, AP 870, TN 1,379. 2,986 of them have coordinates.
- `DISTRICT` is a **police** district, which isn't always a revenue district. Examples: `CYBERABAD-MEDCHAL`, `RAMAGUNDAM-MANCHERIAL`, `AVADI`, `TAMBARAM`, `MADURAI CITY`. Some groupings predate district splits: Vellore (2019) and AP (2022).
- `POLICE STATION` names come in every style: `BORABANDA`, `K-4 ANNANAGAR`, `BHAVANI P.S`, `AWPS ARUPPUKOTTAI`, `RAIPOL (BEGAMPET)`, `II TOWN L AND O KAKINADA`. The same name can appear in several districts and states.
- `STATE` is the only source of which states exist. **Nothing in the code is tied to a particular state**; adding a state means adding rows.

**Sheet `LookupLogs`** gets one row per lookup:
- written by the code: `ADDRESS`, `PREDICTED PS`, `PREDICTED DISTRICT`, `RESULT LOOKUP`, `RESULT MATCH`;
- filled by hand: `FILE NO`, `ACTUAL PS KNOWN`, `PV STATUS`, `MATCH`.

**Loading** (`common/loader.py`): the PoliceStation sheet becomes a DataFrame with values stripped and uppercased. Coordinates are read separately by `v2/geopy_distance.py` with openpyxl, so writes never disturb other sheets or formulas.

---

## 4. The lookup flow, step by step (v2 — the main engine)

Entry is `v2/engine.py::find_best_match(address, known_ps, known_district, df, ai_client)`. The order is designed so **free steps run first and paid steps only when needed**:

```
State filter → Case 1 (typed PS) → Case 2 (typed district) → Case 3a (address names a PS)
            → Case 3b (address names a district) → Case 3n (no state named: nearest anywhere)
            → Case 3c (AI infers district) → Case 0 (nothing)
              free          free/1 geocode           free + 1 geocode          1 geocode
                            1 geocode                AI call + 1 geocode
```

### Step 0 — State filter (always first) — `common/state_filter.py`
The code finds which state(s) from the `STATE` column the address names. It matches full names fuzzily, so `TELENGANA` → TELANGANA and `ANDHRAPRADESH` → ANDHRA PRADESH. Abbreviations like AP/TS are deliberately ignored because they occur inside ordinary text.
- **Exactly one state named:** search only that state's stations. A Telangana address can never get an AP station.
- **None or several:** search all states.

The scope line ("State: … searched") is attached to every result.

### Case 1 — The applicant typed a PS
The typed name is fuzzy-matched against station names (`common/matcher.py::resolve_ps_with_district`, RapidFuzz with three scorers, `FUZZY_CUTOFF = 80`). No geocoding, no AI.
- **Exact match:** VERY HIGH. **Fuzzy match:** HIGH.
- If the name exists in several districts and the typed district picks one, use it. Otherwise return all of them as **MEDIUM** and the officer selects.
- If nothing matches, fall through to the district or address cases.
- ⚠ Given §1 (the typed PS is often a guess), Codex's review notes that stopping here doesn't show the 3 nearest. That's open for the owner to decide.

### Case 2 — The applicant typed a district (no PS, or the PS didn't match)
1. Fuzzy-match the district.
2. **Text-first pin:** if the address text itself names a station *inside that district* (strict locality scan, below), that station is pinned at rank 1.
3. Geocode the address once, measure the real (geodesic) distance to every station in the district, and fill the remaining slots with the nearest.
4. **Nearer neighbour in another district:** the district filter runs *before* any distance is measured, so a station just over the boundary is dropped however close it is. After ranking the district, the same cached coordinates are scanned across every district in scope, and any station at least `CROSS_DISTRICT_MARGIN_KM = 1` km nearer than the district's own best is listed first and marked `*` (at most `CROSS_DISTRICT_MAX = 2`). This costs no extra API call — the address geocode is memoised, and station coordinates were already cached.

   It is **surfaced, never substituted**: the stated district's own ranking stays in the list underneath, because nearest by straight line is not the same as correct jurisdiction. Real example — an address in Ganesh Nagar, Nagole with the district typed as `HYDERABAD` returned stations 4.7–5.5 km away, while NAGOLE PS sat 0.7 km away in MALKAJGIRI-RANGAREDDY.
5. **Sanity warning:** if even the nearest station in the stated district is more than `DISTANCE_WARN_KM = 30` km away, warn that the stated district is probably wrong. Results are unchanged; the officer decides. (Suppressed when a nearer neighbour was already named, which is the more specific finding.)
6. **If the address can't be geocoded:** list the district's stations unranked as LOW and say why. It never pretends to rank.

### Case 3 — Address only (or typed PS/district failed)

**3a. Does the address name a station?** — `find_ps_by_localities`
Locality candidates are extracted from the address (comma/slash segments plus individual words, minus stopwords like FLAT/PLOT/ROAD and the state's own words) and matched **strictly** (`LOCALITY_CUTOFF = 86`) against station names. Four documented invariants stop junk matches:
- **I1:** a minimum signal length, so `H` from `H NO` can never match;
- **I2:** score by evidence, not substring, so `NAGAR` doesn't hit every `*NAGAR` station;
- **I3:** a mass tie means no answer;
- **I4:** sheet order never decides ties.

If stations are named, geocode the address once to verify by distance. Same-name stations are ordered nearest-first, and a named station more than 30 km away is downgraded to LOW with a warning, never dropped.

**3b. Does the address name a district or zone?** (e.g. `SECUNDERABAD`) — `find_district_by_localities`
If so, geocode and rank that district's stations by distance.

This narrows before measuring, exactly as Case 2 does, so it runs the **same cross-district neighbour check**: any station at least `CROSS_DISTRICT_MARGIN_KM` nearer than the district's own best is listed first and marked `*`. The warning says the district was *named in the address*, rather than entered by the officer — so you know which to question.

**3n. No single state named, and 3a/3b found nothing**
Geocode once and return the nearest stations **across all states**.

**3c. Last resort: AI** — `v2/ai_engine.py`
The AI is given the address and the district list for the states being searched (grouped by state, region named from the data). It returns up to 2 districts, each re-validated against the sheet. Then rank by real distance. **This is the only place AI is used in v2, and it only picks a district, never a station.**

### Case 0 — Nothing worked
Return an empty result, honestly.

### After every case — stacked-coordinate guard (added by Codex)
Any shown station whose coordinate is shared with a **differently named** station is marked `coordinate_unverified`. Its confidence drops to LOW, and a warning says the distances can't tell those stations apart (`coordinate_collisions()` in `v2/geopy_distance.py`).

---

## 5. Station coordinates — where distances come from

Distances are geodesic: `geopy.distance.geodesic`, WGS-84 ellipsoid. They run from the geocoded address to each station's stored `LAT`/`LNG`. **Every lookup makes at most one live address geocode.** Station coordinates are geocoded **once** and stored in the sheet; there's no cache file.

**Address geocode** (`geocode_address`): Google Geocoding API with `components={"country": "IN"}` and `language="en"`. Google's best result is **accepted as-is**. Codex briefly made it reject results whose PIN differed from the address PIN, or that were only area-level. On real lookups that returned **no answer at all** for 3 of 26 addresses (one was an exact street match in the neighbouring PIN), so it was reverted. Doubts about the address location are handled by the ladder's warnings, never by discarding the answer.

**Station geocode** (`geocode_station`, used by `scripts/build_ps_coords.py`):
1. Query `"{clean name} Police Station, {DISTRICT}, {STATE}, India"`. `clean_station_name()` strips codes like `K-4 `, the `P.S` suffix and stray dots; the sheet itself is untouched. A row with a blank STATE is skipped, never defaulted.
2. Reject the result if:
   - (a) it's outside India's outer box;
   - (b) Google found only a state/district/taluk centre;
   - (c) its state doesn't match the row's STATE (non-English state names are reverse-geocoded in English first);
   - (d) it's **both** more than 35 km from every other station of its district **and** Google names a different district. This is the "same-name village elsewhere" check, calibrated on the data: the p99 nearest-sibling distance is 21 km, and the wrong results were 41–251 km out.
3. A rejected station stays **blank**. Blank means retry later, never a guess. Hand-entered coordinates are never overwritten.

**Commands:**
- `scripts/build_ps_coords.py` fills blanks, then re-checks the whole new batch before saving.
- `--dry-run` sends no calls and writes nothing.
- `--limit N` runs a trial on N stations.
- `--audit` re-checks stored coordinates; `--audit --fix` clears the bad ones.

**Current state:**
- **2,986 of 3,000 stations have coordinates.** The 14 blanks are listed in CODEX_BRIEF §6.2.
- **395 stations sit on a coordinate shared with a differently named station** (130 points; AP 117, TN 160, TS 118). This is the biggest threat to distance quality; see CODEX_BRIEF §6.1 and CODEX_REVIEW.

---

## 6. v1 vs v2

Same state filter, same matcher, same Case 1/2/3a/3b text rungs. The difference is ranking:
- **v1** (`v1/engine.py`, `v1/ai_engine.py`): the AI ranks stations and **estimates** distances. No Google key is needed, but its distances aren't measured.
- **v2:** real geocoding and measured distances, with AI only to infer a district. **v2 is the one that fits the §1 goal (true nearest + true distances).**

Whether to keep v1 is an open question for the owner.

---

## 7. Logging — `common/lookup_log.py`

After a lookup, the officer chooses which result row they used (or the top one is taken in one-shot mode). That record is appended to `LookupLogs`.

**Limit:** only the chosen station is logged, not all three candidates and their distances. (A SHOWN STATIONS column was tried on 2026-10-01 and removed the same day at the owner's request.) That makes the §1 success measure ("were the shown stations the true nearest?") impossible to reconstruct afterwards. The sheet's `MATCH` formula also compares names exactly, which is the wrong metric for §1. Both points are covered in CODEX_REVIEW.

---

## 8. Configuration — `common/config.py` (v2 re-exports via `v2/config.py`)

| Setting | Value | Meaning |
|---|---|---|
| `FUZZY_CUTOFF` | 80 | Typed-name match threshold |
| `LOCALITY_CUTOFF` | 86 | Stricter threshold for address-text scans |
| `MIN_LOCALITY_LEN` / `MAX_TIE_WIDTH` | 4 / 5 | Matcher invariants I1 / I3 |
| `TOP_N` | 3 | Results shown |
| `STATE_MATCH_CUTOFF` | 85 | State and district name fuzziness |
| `DISTANCE_WARN_KM` (in `v2/config.py`) | 30 | Warn when the nearest station is implausibly far |
| `SIBLING_MAX_KM` / `SIBLING_MIN_COUNT` | 35 / 3 | Same-name-village check for station geocodes |
| `COORD_*` | India box | Outer sanity bound only |
| `GEOCODE_COUNTRY` | IN | Hard filter on every geocode |
| `AI_PROVIDER` / `AI_MODEL` | anthropic / per provider | anthropic \| openai \| gemini |

Keys are read from the environment or `.env`: `GOOGLE_MAPS_API_KEY`, plus one AI key. See `common/api_keys.py`.

---

## 9. Cost per lookup

| Lookup kind | Cost |
|---|---|
| Typed PS (Case 1) | Free |
| District or address with a station/district named (2, 3a, 3b) | 1 Geocoding call (about US$0.005 list price, after the free tier) |
| No state named (3n) | 1 call |
| AI fallback (3c) | 1 AI call + 1 Geocoding call |

Station geocoding is a one-time bulk cost (about 3,000 calls so far). Blank stations are retried, so CODEX_REVIEW suggests a cooldown ledger.

---

## 10. Testing

- **`tests/validate_test_cases.py`:** 22 checks covering real Telangana addresses, v1/v2 parity, duplicates, state filtering and distance rules. Google and the AI are mocked. **This defines the expected behaviour and must stay ALL GREEN.**
- **`tests/test_safety.py`:** 7 tests covering the TN alias, the stack detector, the neighbouring-PIN acceptance, the no-retry of blank stations, the stateful coordinate lookup, collision-safe writes and no-result logging. **7 passed.**
- **Real-lookup check:** run the 26 officer-labelled lookups in `LookupLogs` through `find_best_match` (address only) and report: empty answers, officer's station in the top 1 and in the top 3. **Restored baseline: 0 empty, top-1 = 7, top-3 = 11.** No change may make these worse. This costs about 26 Geocoding calls plus a few AI calls; print counts only, never the addresses.

**Gaps:**
- the real-address cases are Telangana-only;
- there are no tests for the §5 station-geocode checks;
- real-world accuracy is unmeasured — and it should be measured as **"were the true nearest stations in the top 3, with true distances"**, not as exact-name match.

---

## 11. Project rules to keep

1. **Never edit the sheet's rows.** The data comes from GPSP as-is. Only `LAT`/`LNG` and `LookupLogs` are written.
2. **Nothing tied to a region.** Any state added to the sheet must work with no code change.
3. **Never show a station that isn't in the sheet.** The AI only narrows; the sheet answers.
4. **Blank beats wrong.** A doubtful coordinate is left blank and reported, never saved.
5. **Honest output.** Say what was searched, why, and what couldn't be checked. Never overstate certainty.
6. **Paid calls:** trial small, show the owner, then run in bulk. Back up the Excel before any bulk write.
7. **Keep the flow.** The ladder and case structure work. Improve inside them, don't redesign.
8. **Version control:** the folder is still **not a git repo**. Initialise it and commit a baseline before further edits, now that two agents are changing code.

---

## 12. History: the address-first experiment (2026-10-01)

Codex replaced the ladder with "geocode the address → show the 3 nearest in the state", ignoring the address text and the typed PS/district. It was tested against the 26 real lookups:

| | Restored ladder | Address-first |
|---|---|---|
| Empty answers | **0** | 3 |
| Officer's station in top 3 | 11 | 16 |
| Officer's station #1 | 7 | 10 |
| Fewer than 3 stations shown | 13 | 0 |

**The owner chose the ladder:** it worked well, and no lookup may return nothing. The address-first code is preserved in git commit `bdb9634`.

Its strengths ("always show 3", for example) may come back **only as additions inside the ladder**: proposed first, measured on the real lookups, and approved by the owner. They must never replace the ladder.
