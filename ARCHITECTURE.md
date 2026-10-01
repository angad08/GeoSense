# GeoSense architecture

## Current v2 address flow

```text
Address (+ optional applicant PS/district guess)
  → common.loader reads PoliceStation rows
  → common.state_filter uses STATE values in the sheet
  → Google Geocoding resolves and checks the address (one forward call; occasional reverse state check)
  → v2.geopy_distance measures to all located rows in the scope
  → v2.engine sorts by distance and displays three physical candidates
  → common.lookup_log records the selected row or a no-result event
```

`STATE` is data-driven. If the address names exactly one state in the sheet, that state is the search scope and must agree with Google's result. If it names none or several, Google's returned state must match exactly one state in the sheet. The ranking is then limited to that state. A Google result that conflicts with a detected state or input PIN is rejected. State or district centre results are rejected. A distance ranking cannot be made when the address geocode or state check fails.

Applicant-provided PS and district names are **hints** for an address lookup. They never override distances or exclude nearby stations. A name-only PS lookup still resolves the sheet row locally without Google. `v1` retains the older AI/text approach and is a separate historical option, not the v2 address-ranking path.

Station coordinates are stored only in the `LAT`/`LNG` columns of `PoliceStation`. Normal lookups read them and never attempt to fill missing station coordinates. The explicit `scripts/build_ps_coords.py` maintenance command geocodes blank rows, validates India/state/result type and sibling context, and rejects new exact-coordinate collisions between different names. Its dry run makes no API calls. The existing 395 stacked rows remain in the workbook and are flagged as uncertain at lookup time. A real co-location is possible, so coordinates must be verified before correction.

The distance is WGS-84 geodesic distance to the stored station coordinate. It is neither travel time nor a legal jurisdiction assignment. The display keeps each candidate's sheet station name, district, distance and review status. Same-name rows at the same coordinate are collapsed **only in the displayed candidate list** so historical district copies do not consume multiple of the three slots; source rows remain untouched.

## Main modules

| Module | Responsibility |
|---|---|
| `common/loader.py` | Read and normalize sheet values in memory |
| `common/state_filter.py` | Derive searchable states from `STATE` |
| `v2/geopy_distance.py` | Validate the address geocode, load station coordinates, detect shared points, calculate distance |
| `v2/engine.py` | Return three nearest located rows and surface missing/uncertain coordinates |
| `common/output.py` | Print candidates and distances with review wording |
| `common/lookup_log.py` | Append selected and no-result events to `LookupLogs` |
| `scripts/build_ps_coords.py` | Explicit coordinate maintenance and audit |

`--excel PATH` configures the coordinate layer to use the same workbook loaded by the CLI and written by the log. The source station sheet is never merged or deduplicated. `tests/validate_test_cases.py` tests the current nearest-three rule with a mocked geocoder; `tests/test_safety.py` covers geocode rejection, coordinate stacks, and retry suppression. The previous ladder test is retained as `tests/legacy_validate_test_cases.py` for history and is not a current acceptance gate.

## Remaining measurement gap

The existing `LookupLogs` sheet stores only the selected station, not the full three candidates and distances. Its `MATCH` formula compares names exactly, which does not test the owner's proximity objective. A prospective review should record all three displayed candidates and the officer's acceptable nearby stations, then measure top-three coverage and distance quality separately by state. See [CODEX_REVIEW.md](CODEX_REVIEW.md).
