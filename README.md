# GeoSense

> **Note (2026-10-01):** the lookup flow has been restored to the original ladder (fuzzy → locality scan → geocode/distance → AI). Parts of this page still describe a short-lived "address-first nearest-three" version and are out of date until the original page is restored. **The accurate description is [GEOSENSE_EXPLAINED.md](GEOSENSE_EXPLAINED.md).**

GeoSense helps an officer choose a nearby police station for a passport-verification address. It reads real station rows from `data/POLICE_STATION.xlsx`, geocodes the address once, and displays the **three nearest located stations with distances**. An applicant-supplied PS or district may be a guess; when an address is present, neither restricts the search.

The officer selects among the nearby candidates. An exact match to one previously recorded station name is not the success criterion: several stations can be similarly close. GeoSense measures straight-line distance, not legal jurisdiction or travel time.

## Run

Install the dependencies in `requirements.txt` and set `GOOGLE_MAPS_API_KEY` for v2 address searches. Close the workbook in Excel before running a lookup, since the result is logged to `LookupLogs`.

```bash
python main.py --address "7-8-237 Goutham Nagar, Ferozguda, Balanagar, Telangana 500011"
python main.py --address "..." --ps "applicant's guess" --district "applicant's district"
python main.py --ps "Gachibowli"     # name-only reference lookup; no Maps call
python main.py                     # interactive
```

An address lookup normally makes **one Geocoding API call** and no AI call. When the address names exactly one state present in the workbook, that state is checked against Google's result. Otherwise, Google's returned state determines the search scope. If the state cannot be matched to exactly one workbook state, no ranking is shown. A supplied PS or district is shown as context in the method, never used as a hard filter for an address. `--excel PATH` uses that workbook for matching, coordinates, and logging.

If Google cannot locate the address with enough confidence, GeoSense returns no distance ranking and logs the no-result case. If Google returns a conflicting PIN or state, or only a broad district/state centre, the address geocode is rejected. Blank station coordinates are excluded and counted. A coordinate shared with a differently named station is marked uncertain; its displayed distance cannot distinguish those stations. Review labels are prompts to check the candidates, not calibrated probabilities.

## Workbook contract

The `PoliceStation` sheet has `DISTRICT`, `POLICE STATION`, `STATE`, `LAT`, and `LNG` columns. All source rows are retained exactly as supplied, including repeated names and historical district listings. Code-side normalization shapes search queries only; it never renames, merges, or deletes station rows. The application writes only `LAT`/`LNG` during explicit coordinate maintenance. A normal address lookup does not retry blank station coordinates.

`LookupLogs` records the selected station and district, or a no-result lookup. Its historical `MATCH` formula compares station names exactly; that is **not** a valid measure of whether three useful nearby candidates were offered. A future evaluation needs the full three displayed names and distances and an officer's assessment of acceptable nearby choices. See [CODEX_REVIEW.md](CODEX_REVIEW.md) for the baseline findings and remaining data work.

## Coordinate maintenance

```bash
python scripts/build_ps_coords.py --dry-run       # no API calls, no writes
python scripts/build_ps_coords.py --limit 20       # first 20 blank rows; validation can add calls
python scripts/build_ps_coords.py                  # explicit full fill
python scripts/build_ps_coords.py --audit          # may call Google for isolated rows
```

The builder leaves a station blank when Google finds only an area centre, places it in the wrong state, fails the sibling/district check, or returns a coordinate shared by a differently named station. Exact co-location can be legitimate; investigate those rows and enter independently verified coordinates rather than automatically deleting source rows. The current workbook has 14 blank coordinates and 395 rows at different-name shared points, as measured in the review.

## Tests and limits

```bash
python tests/validate_test_cases.py
python -m unittest tests.test_safety
```

These tests mock Google and make no API calls. `tests/legacy_validate_test_cases.py` preserves the earlier text-ladder checks for reference; they describe behavior replaced by the address-first ranking rule. Live top-three proximity quality remains unmeasured for Telangana, Andhra Pradesh, and Tamil Nadu. The workbook's 26 officer-confirmed station names can inform a review, but the historical log omitted the other candidates and their distances.

See [QUICKSTART.md](QUICKSTART.md) for setup commands and [ARCHITECTURE.md](ARCHITECTURE.md) for the current flow. `v1` remains available as the earlier AI-estimated approach; it does not follow v2's address-first nearest-three rule and is not a measured substitute for v2.
