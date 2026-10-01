# Quick start

> **Note (2026-10-01):** the lookup flow has been restored to the original ladder (fuzzy → locality scan → geocode/distance → AI). Parts of this page still describe a short-lived "address-first nearest-three" version and are out of date until the original page is restored. **The accurate description is [GEOSENSE_EXPLAINED.md](GEOSENSE_EXPLAINED.md).**

GeoSense v2 displays the three nearest located police-station rows for an address. A guessed station or district supplied with the address does not restrict the search.

1. Close `data/POLICE_STATION.xlsx` in Excel.
2. Install `requirements.txt` in a Python environment.
3. Set `GOOGLE_MAPS_API_KEY` and enable the Google Geocoding API for that key.
4. Run:

```bash
python main.py --address "7-8-237 Goutham Nagar, Ferozguda, Balanagar, Telangana 500011"
```

The table shows up to three real station rows and their geodesic distances. A normal address lookup makes one Geocoding API call; if Google returns an ambiguous address result, GeoSense shows no distance ranking. The selected result or no-result event is appended to `LookupLogs`.

To test without API calls:

```bash
python tests/validate_test_cases.py
python -m unittest tests.test_safety
```

To inspect station coordinate work before spending on Google calls:

```bash
python scripts/build_ps_coords.py --dry-run
```

See [README.md](README.md) for the workbook contract and [CODEX_REVIEW.md](CODEX_REVIEW.md) for the data-quality review.
