"""
GeoSense — common/output.py  (shared)
--------------------------------------
Formats and prints query results as a clean table. Shared by v1 and v2.

A result may also carry a warning or note about address precision, missing
coordinates, or shared station coordinates. These are printed under the table.

Every result also carries `state_scope` (common/state_filter.py), printed under
the table so it is always clear which state's stations were searched.
"""

import textwrap

from tabulate import tabulate

# Human-readable confidence labels, shown in the output table and reused by
# the lookup log so the logged wording always matches what was displayed.
SURETY_LABELS = {
    "VERY HIGH": "Strong lead — verify",
    "HIGH":      "Lead — verify",
    "MEDIUM":    "Possible — verify",
    "LOW":       "Uncertain — review",
    "NONE":      "No suggestion",
}


def print_output(result):
    """
    Display a result dict (from engine.find_best_match) as a clean table.
    No technical jargon — surety labels are plain English.
    """
    sep = "-" * 50
    if not result["results"]:
        print(f"\n{sep}\nNo nearby stations could be ranked.\n{sep}")
        if result.get("method"):
            print(f"  Method: {result['method']}")
        if result.get("state_scope"):
            print(f"  {result['state_scope']}")
        if result.get("warning"):
            print(f"  [!] {result['warning']}")
        return

    rows = []
    for r in result["results"]:
        surety = SURETY_LABELS.get(r["confidence"], r["confidence"])
        rows.append([r["rank"], r["police_station"], r["district"],
                     r.get("state", ""), surety, r.get("distance", "N/A")])

    print(f"\n{sep}")
    print(tabulate(rows, headers=["#", "Police Station", "District", "State",
                                 "Assessment", "Distance"], tablefmt="simple"))
    print(sep)
    print("  Compare the nearby candidates and their distances before selecting.")
    if result.get("method"):
        print(f"  Method: {result['method']}")

    scope = result.get("state_scope")
    if scope:
        print(f"  {scope}")

    warning = result.get("warning")
    if warning:
        print()
        print(textwrap.fill(warning, width=72,
                            initial_indent="  [!] ", subsequent_indent="      "))
        print()

    note = result.get("note")
    if note:
        print(textwrap.fill(note, width=72,
                            initial_indent="  [Note] ", subsequent_indent="         "))
