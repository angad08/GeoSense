#!/usr/bin/env python3
"""
GeoSense — scripts/build_ps_coords.py  (optional bulk warm-up)
---------------------------------------------------------------
Fills the LAT / LNG columns of the PoliceStation sheet for every station that
does not have coordinates yet, and saves them back into the same Excel file.
There is no separate cache file — the Excel is the single source of truth.

Run this explicitly when station coordinates need enrichment. Ordinary v2
lookups do not retry failed stations or write new coordinates.

Safe to re-run: stations that already have coordinates are skipped, so a re-run
after adding rows to the Excel geocodes only the new ones. Nothing is
overwritten — including coordinates you filled in by hand.

Each query is built from the station's own row:
    "{PS_NAME} Police Station, {DISTRICT}, {STATE}, India"
with the name cleaned for search only (station codes like "K-4 ", stray dots and
"P.S" removed; the sheet is never changed). A station whose STATE is blank is
skipped, never given a default state. A result Google places in a different
state than the row's STATE, or only at a district / taluk centre, is rejected
unwritten.

Stations that fail to geocode or share a point with a differently named station
are left blank and listed at the end. They are retried only on a later explicit
run. Keep the source station name intact and investigate aliases or verified
coordinates outside this script.

Usage (from the project root, with the Excel file CLOSED):
    export GOOGLE_MAPS_API_KEY=your_key_here
    python scripts/build_ps_coords.py

    python scripts/build_ps_coords.py --dry-run
        Prints the query each unresolved station would get, plus a count per
        state. No API calls, no API key needed, nothing written.

    python scripts/build_ps_coords.py --restack [--limit N] [--fix]
        Stations sharing a point with differently named stations: look up the
        village / town each is named after and show where it would move (one
        Geocoding call per station). With --fix the moves are saved. A station
        whose place cannot be confirmed keeps its current point.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

# Make the project root importable no matter how this file is launched.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import EXCEL_FILE, SHEET_NAME, SEARCH_ALIAS_FILE
from v2.geopy_distance import (
    _load_coords_cache, _state_cache, _write_coords, _clear_coords,
    geocode_station, station_geocode_query, audit_station,
    coordinate_collisions, geocode_station_place,
    resolve_station, record_alias,
)

NO_STATE = "(STATE blank - would be skipped)"


def dry_run(missing):
    """Print every query that would be sent, and a count per state.
    No API calls, no writes."""
    per_state = Counter()
    for district, ps in missing:
        state = _state_cache.get((district, ps), "")
        query = station_geocode_query(ps, district, state)
        per_state[state or NO_STATE] += 1
        print(f"  {query}" if query else f"  [SKIP] {ps} ({district}) - STATE is blank")

    print("\nPer state (stations needing coordinates):")
    for state, n in sorted(per_state.items()):
        print(f"    {state:34} {n}")
    print("\nDry run - no API calls made, nothing written.")


def audit(cache, fix):
    """Report sibling outliers and coordinate stacks. Isolated rows may
    trigger a Geocoding call. --fix clears only sibling outliers; stacks need
    independent review because some are genuine colocations."""
    stored = [(k, v) for k, v in cache.items() if v is not None]
    print(f"Auditing {len(stored)} stored coordinate(s) ...\n", flush=True)
    stacks = coordinate_collisions(cache)
    print(f"  REVIEW  {len(stacks)} station coordinate(s) share a point with "
          "a differently named station; --fix does not clear these.")
    bad = []
    for (district, ps), (lat, lng) in stored:
        reason = audit_station(district, ps, lat, lng)
        if reason:
            bad.append((district, ps))
            print(f"  SUSPECT  {ps} ({district}) [{_state_cache.get((district, ps), '')}]: {reason}", flush=True)
    print(f"\n{len(bad)} suspect coordinate(s).")
    if bad and fix:
        _clear_coords(bad)
    elif bad:
        print("Re-run with --audit --fix to clear them.")


def restack(cache, fix, limit=0):
    """
    Move stations off shared points to their own village / town. Preview unless
    `fix`. A move is kept only if, with the whole batch applied, the new point
    is not shared with a differently named station; otherwise the station keeps
    its current point. Nothing is ever cleared here.
    """
    stacked = sorted(coordinate_collisions(cache))
    print(f"Stacked  : {len(stacked)} station(s) share a point with a differently "
          f"named station")
    if limit > 0:
        stacked = stacked[:limit]
        print(f"--limit {limit}: only the first {len(stacked)} are checked.")
    print()

    moves, width = {}, len(str(len(stacked)))
    for n, (district, ps) in enumerate(stacked, start=1):
        new, detail = geocode_station_place(district, ps, cache)
        tag = f"  [{n:>{width}}/{len(stacked)}]"
        if new:
            moves[(district, ps)] = new
            print(f"{tag} MOVE  {ps} ({district}) -> {detail}", flush=True)
        else:
            print(f"{tag} KEEP  {ps} ({district}) - {detail}", flush=True)

    # Two moves may land on one town point (ADILABAD I TOWN / II TOWN). Drop
    # every move that still collides, until the batch is clean.
    while True:
        proposed = dict(cache)
        proposed.update(moves)
        clash = coordinate_collisions(proposed) & set(moves)
        if not clash:
            break
        for key in sorted(clash):
            print(f"  KEEP  {key[1]} ({key[0]}) - its town point is shared with "
                  "another station", flush=True)
            moves.pop(key)

    after = len(coordinate_collisions(proposed))
    print()
    print(f"Would move : {len(moves)}")
    print(f"Stacked    : {len(coordinate_collisions(cache))} before -> {after} after")
    if not moves:
        return
    if fix:
        _write_coords([(d, p, la, ln) for (d, p), (la, ln) in moves.items()])
    else:
        print()
        print("Preview only - nothing written. Re-run with --fix to save "
              "(close the Excel first).")


def main():
    parser = argparse.ArgumentParser(
        description="Fill missing station LAT/LNG in the PoliceStation sheet.")
    parser.add_argument("--limit", type=int, default=0,
                        help="geocode only the first N missing stations "
                             "(a trial run before the full fill)")
    parser.add_argument("--audit", action="store_true",
                        help="re-check stored coordinates for same-name places "
                             "far from their district and report coordinate stacks; "
                             "isolated rows may require API calls")
    parser.add_argument("--fix", action="store_true",
                        help="with --audit: clear the suspect coordinates; "
                             "with --restack: save the moves")
    parser.add_argument("--restack", action="store_true",
                        help="move stations that share a point with differently "
                             "named stations to their own village / town "
                             "(one Geocoding call each; preview unless --fix)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the geocode queries and per-state counts; "
                             "no API calls, no writes")
    args = parser.parse_args()

    cache   = _load_coords_cache()
    missing = [key for key, coords in cache.items() if coords is None]

    print(f"Workbook : {EXCEL_FILE}")
    print(f"Sheet    : {SHEET_NAME}")
    print(f"Stations : {len(cache)} total, {len(missing)} without coordinates\n")

    if args.audit:
        audit(cache, args.fix)
        return

    if args.restack:
        restack(cache, args.fix, args.limit)
        return

    if not missing:
        print("Nothing to do — every station already has coordinates.")
        return

    if args.limit > 0:
        missing = missing[:args.limit]
        print(f"--limit {args.limit}: only the first {len(missing)} are processed.\n")

    if args.dry_run:
        dry_run(missing)
        return

    updates, failed = [], []
    total, width = len(missing), len(str(len(missing)))

    # One line per station, printed as it happens, so a long run never looks
    # frozen. Nothing is written until the end — the Excel is saved once.
    print(f"Geocoding {total} station(s) — one line each. The Excel is saved "
          f"once, at the end.\n", flush=True)

    pending_alias, tried = {}, {}

    for n, (district, ps) in enumerate(missing, start=1):
        coords = geocode_station(district, ps)   # None → skipped, failed or rejected
        tag    = f"  [{n:>{width}}/{total}]"
        how    = ""
        if not coords:
            # The default phrasing failed. Walk the ladder of alternatives
            # before giving up, and remember whichever one works so the next
            # run — and the next state added — does not have to search again.
            state = _state_cache.get((str(district).strip().upper(),
                                      str(ps).strip().upper()), "")
            coords, name, mode, why, attempts = resolve_station(district, ps, state)
            if not coords and attempts:
                # Every phrasing was refused. Show the whole trail — the query
                # sent, and what came back — because this is the station a human
                # now has to resolve, and guessing from one line costs more than
                # printing four.
                tried[(district, ps)] = attempts
            if coords:
                how = f" (resolved: {why})"
                # Held, not written yet: the batch sibling re-check below can
                # still reject this coordinate, and an alias recorded for a
                # rejected point would claim a phrasing works when it does not.
                pending_alias[(district, ps)] = (name, mode, why)
        if not coords:
            # Last resort: the village / town it is named after, same checks.
            coords, detail = geocode_station_place(district, ps, cache)
            how = f" (its town: {detail.split(',')[0]})" if coords else ""

        if coords:
            lat, lng = coords
            updates.append((district, ps, lat, lng))
            print(f"{tag} OK     {ps} ({district}) -> {lat:.5f}, {lng:.5f}{how}",
                  flush=True)
        else:
            # Left blank in the sheet, never dropped — retried next run.
            # geocode_station() has already printed the reason above.
            failed.append(f"{ps} ({district})")
            print(f"{tag} BLANK  {ps} ({district}) — left blank, see warning above",
                  flush=True)

    # Sibling re-check with the whole batch in view: during the loop a new
    # district had too few stored stations to judge, now it has them all.
    combined = dict(cache)
    combined.update({(d, p): (la, ln) for d, p, la, ln in updates})
    kept = []
    for d, p, la, ln in updates:
        reason = audit_station(d, p, la, ln, combined)
        if reason:
            failed.append(f"{p} ({d})")
            print(f"  [WARN] Rejected {p} ({d}): {reason} — likely a same-name "
                  f"place elsewhere, left blank.", flush=True)
        else:
            kept.append((d, p, la, ln))
    # Detect same-point matches against both stored coordinates and the entire
    # pending batch. This also works when a new state has no stored siblings.
    proposed = dict(cache)
    proposed.update({(d, p): (la, ln) for d, p, la, ln in kept})
    colliding = coordinate_collisions(proposed)
    updates = []
    for d, p, la, ln in kept:
        if (d, p) in colliding:
            failed.append(f"{p} ({d})")
            print(f"  [WARN] Review {p} ({d}): coordinate is shared with a "
                  "differently named station — left blank.", flush=True)
        else:
            updates.append((d, p, la, ln))

    if updates:
        print(f"\nSaving {len(updates)} coordinate(s) to {EXCEL_FILE.name} ...", flush=True)
        _write_coords(updates)

    # Only now, for the coordinates that actually survived every check. A
    # phrasing is only "known to work" if what it produced was good enough to
    # write; recording it earlier would put a false claim in the alias file.
    learned = []
    for d, p, _la, _ln in updates:
        found = pending_alias.get((d, p))
        if found and record_alias(d, p, *found):
            learned.append(f"{p} ({d}) -> {found[0]} [{found[1]}] — {found[2]}")

    print(f"\nGeocoded : {len(updates)}")

    if learned:
        print(f"\nLearned {len(learned)} new search alias(es) — written to "
              f"{SEARCH_ALIAS_FILE.name}, so these resolve directly next time:")
        for line in learned:
            print(f"    - {line}")
        print("  Review them like any other data: the NOTE column says what "
              "each one assumed.")

    print(f"\nNot filled (skipped / failed / rejected) : {len(failed)}")
    for name in failed:
        print(f"    - {name}")
        # The trail for this station, if the ladder ran: every query sent and
        # what came back. This is what turns "still blank" into something a
        # person can act on without re-running anything.
        for (d, p), attempts in tried.items():
            if name == f"{p} ({d})":
                for query, reason in attempts:
                    print(f"        tried: {query}")
                    print(f"               -> {reason}")

    if failed:
        print("\nEvery phrasing was refused for these, so they need a human: "
              "check the station name and STATE in the Excel, or add a row to "
              f"{SEARCH_ALIAS_FILE.name} with a name that does exist (SEARCH AS "
              "= place for a town, station for a station). Two stations sharing "
              "one town cannot be separated by geocoding at all — those need "
              "coordinates read off a map.")


if __name__ == "__main__":
    main()
