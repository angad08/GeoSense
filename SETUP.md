# Setup

## Python and packages

Use Python 3 with the packages in `requirements.txt`:

```bash
python -m pip install -r requirements.txt
```

The current v2 address path needs `pandas`, `openpyxl`, `geopy`, `googlemaps`, `rapidfuzz`, and `tabulate`. The listed AI-provider package is used by the older v1 path; v2's nearest-three address path makes no AI call.

## Workbook

Keep `data/POLICE_STATION.xlsx` in the project. It must have a `PoliceStation` sheet with `DISTRICT`, `POLICE STATION`, `STATE`, `LAT`, and `LNG`, plus a `LookupLogs` sheet with the expected headers. Pass `--excel PATH` if using another workbook; v2 uses that path for matching, coordinates, and logging.

Close the workbook in Excel before running any command that logs a lookup or fills coordinates. The source station rows must remain as supplied; only `LAT`/`LNG` are written by coordinate maintenance.

## Google key

Enable the Google Geocoding API for your key and set `GOOGLE_MAPS_API_KEY` in your environment or a local `.env` file. A v2 address lookup normally uses one forward Geocoding call, with an occasional reverse check for a state name returned in local script. A typed station lookup without an address needs no Maps call.

```bash
python main.py --address "10 Main Road, Chennai, Tamil Nadu 600001"
python main.py --ps "Gachibowli"
```

An address lookup displays up to three nearest located source rows and their geodesic distances. Applicant-supplied `--ps` and `--district` values alongside an address are hints and do not filter the distance search.

## Safe checks

```bash
python tests/validate_test_cases.py
python -m unittest tests.test_safety
python scripts/build_ps_coords.py --dry-run
```

These commands are intended to make no API calls or workbook writes. The explicit coordinate builder without `--dry-run` makes paid Google calls and can fill blank `LAT`/`LNG` cells. Its `--audit` mode may also make Google calls for isolated rows.

If Python is unavailable, install it before relying on the changes. The 2026-10-01 code changes could not be executed in the review environment because neither `python` nor `py` was on PATH.
