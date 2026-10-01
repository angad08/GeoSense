# Changelog

What changed in GeoSense, newest first. Code changes are in git; changes to the
Excel (`data/POLICE_STATION.xlsx`, not committed) are recorded here because git
cannot show them.

---

## 2026-10-01

### Output

- **Confidence column.** The results table's `Assessment` header is now
  `Confidence`. The labels are unchanged (Guaranteed / Very Likely / Likely /
  Possible / Unknown), so `LookupLogs` → `RESULT MATCH` stays consistent.
- **State column only when needed.** It was always blank: the all-states search
  never carried the station's state. It now does, and the column appears only
  for that search (no station, district or state to go on). Other lookups stay
  inside one state, so the column is left out.
- **State line only when true.** "State: not named in address — all states
  searched" was printed even when a known station or district limited the
  search. It now prints only when every state was searched or one state was
  named in the address.
- **SHOWN STATIONS removed.** The column added to `LookupLogs` earlier the same
  day (`f00c8f3`) was reverted at the owner's request. `LookupLogs` again records
  only the chosen station. Old SHOWN STATIONS cells in the Excel are left as
  they are; delete the column by hand if wanted.

### Station coordinates

- **Search names** — `data/station_search_names.csv` (DISTRICT, POLICE STATION,
  SEARCH NAME). For stations Google cannot find by their official name, the
  build script searches the name Google knows instead. The Excel name is never
  changed, normal lookups never read the file, and every safety check still
  applies. See README → *Station Coordinates*.
- **Fill from own town** (`4c4cdd1`). When the "X Police Station" search fails,
  `build_ps_coords.py` tries the village / town the station is named after,
  under the same checks.
- **`--restack`** (`d724e51`). Moves stations that share a point with a
  differently named station to their own village / town. Preview unless
  `--fix`; a move is kept only if it lands clear of every other station.

### Excel changes (LAT / LNG only; names and rows untouched)

Blank stations went from 10 to 2. Backups were taken before each step
(`data/POLICE_STATION.backup-2026-10-01-*.xlsx`).

| Station (district) | What was done |
|---|---|
| RAIPOL (BEGAMPET), Siddipet | Filled — searched as BEGAMPET RAIPOLE (station renamed Begampet; same building in Raipole) |
| TOWN CENTRAL, The Nilgiris | Filled — searched as OOTY CENTRAL |
| ETHAKOIL, Theni | Filled — searched as ETHAKOVIL |
| PERUGAVALTHAN, Thiruvarur | Filled — village Perugavazhndan |
| T T PETTAI, Tiruchirappalli Rural | Filled — searched as THATHAIYANGARPETTAI |
| CHENAM, Tiruvannamalai | Filled — searched as CHENGAM (no other Chengam station in the district) |
| T.V.NALLUR, Viluppuram | Filled — searched as THIRUVENNAINALLUR |
| BAZAAR, Ramanathapuram | Filled — searched as RAMANATHAPURAM BAZAAR |
| AURUVILE, Viluppuram | Moved 50.7 km to Auroville (was stacked on Thiruvennainallur) |
| BRAMMDESAM, Viluppuram | Moved 31.1 km to Brahmadesam (same stack) |
| SIKKAL, Ramanathapuram | Moved 25.5 km to Sikkal (was stacked on Ramanathapuram town) |
| THIRUPPULANI, Ramanathapuram | Moved 9.0 km to Thirupullani (same stack) |
| RAMANATHAPURAM TOWN, Ramanathapuram | Moved 0.9 km to the town centre (was on the Bazaar station's point) |

**Still blank:** ANNAIKATTU (Chengalpattu) and KOVILPALAYAM (Ramanathapuram).
Names and districts are correct per GPSP, but Google only knows same-name places
in Vellore (94 km) and Coimbatore (232 km). Enter verified LAT / LNG by hand.
Until then they can be matched by name but are left out of distance ranking.

### Matching

- **TN / AP name formats** (`8feb865`). "ALL WOMEN PS BODI" = "BODI AWPS";
  a station also matches without its bracket or U/G suffix when that short
  form is unique. A station listed under two districts at the same point
  (e.g. VELLORE / RANIPET) is shown once.

### Restorations

- **Lookup ladder restored** (`a88e40d`). v2 runs the original ladder again
  (fuzzy → locality scan → geocode / distance → AI). Codex's address-first
  version is kept in `bdb9634` for comparison.
- **Original docs restored** (`b1c8c9b`). ARCHITECTURE, CONTRIBUTING,
  QUICKSTART, SETUP and README back to the owner's versions, with the
  Telangana / Andhra Pradesh / Tamil Nadu scope reapplied.

### Docs

- README corrected: lookups do not geocode blank stations (only
  `build_ps_coords.py` does); the coordinate envelope is India's outer box,
  not Telangana + Andhra Pradesh.

### Checks

28 pytest tests pass; the 22-check regression suite
(`tests/validate_test_cases.py`) is ALL GREEN.
