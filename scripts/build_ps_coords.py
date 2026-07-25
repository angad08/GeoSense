#!/usr/bin/env python3
"""
GeoSense — scripts/build_ps_coords.py  (optional bulk warm-up)
---------------------------------------------------------------
Fills the LAT / LNG columns of the PoliceStation sheet for every station that
does not have coordinates yet, and saves them back into the same Excel file.
There is no separate cache file — the Excel is the single source of truth.

This script is OPTIONAL. v2 fills missing coordinates by itself, on demand, the
first time a station is actually needed (see v2/geopy_distance.py). Run this
only when you would rather pay the whole geocoding cost once, up front, than
have the first lookup in a district be a little slower.

Safe to re-run: stations that already have coordinates are skipped, so a re-run
after adding rows to the Excel geocodes only the new ones. Nothing is
overwritten — including coordinates you filled in by hand.

Stations that fail to geocode are left blank and listed at the end. They are
retried on the next run or the next lookup, so a transient API problem never
becomes a permanent hole. A station that keeps failing usually needs its name
corrected in the Excel.

Usage (from the project root, with the Excel file CLOSED):
    export GOOGLE_MAPS_API_KEY=your_key_here
    python scripts/build_ps_coords.py
"""

import sys
from pathlib import Path

# Make the project root importable no matter how this file is launched.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import EXCEL_FILE, SHEET_NAME, GEOCODE_SUFFIX
from v2.geopy_distance import _load_coords_cache, _write_coords, geocode_address


def main():
    cache   = _load_coords_cache()
    missing = [key for key, coords in cache.items() if coords is None]

    print(f"Workbook : {EXCEL_FILE}")
    print(f"Sheet    : {SHEET_NAME}")
    print(f"Stations : {len(cache)} total, {len(missing)} without coordinates\n")

    if not missing:
        print("Nothing to do — every station already has coordinates.")
        return

    updates, failed = [], []

    for district, ps in missing:
        query  = f"{ps} Police Station, {district}, {GEOCODE_SUFFIX}"
        result = geocode_address(query)          # returns None on any failure

        if result:
            (lat, lng), _ = result
            updates.append((district, ps, lat, lng))
        else:
            # Left blank in the sheet, never dropped — retried next run.
            failed.append(f"{ps} ({district})")
            print(f"  [WARN] Could not geocode: {query}")

    if updates:
        _write_coords(updates)

    print(f"\nGeocoded : {len(updates)}")
    print(f"Failed   : {len(failed)}")
    for name in failed:
        print(f"    - {name}")

    if failed:
        print("\nThese are still blank in the sheet and will be retried "
              "automatically.\nIf one keeps failing, check its spelling in the "
              "Excel.")


if __name__ == "__main__":
    main()
