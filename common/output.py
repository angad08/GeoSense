"""
GeoSense — common/output.py  (shared)
--------------------------------------
Formats and prints query results as a clean table. Shared by v1 and v2.

A result may also carry an advisory `warning` (v2 Case 2 — see v2/engine.py).
It is printed under the table for the human to act on; the results above it
stand unchanged either way. v1 results never carry a warning, so that block
simply never fires for v1.
"""

import textwrap

from tabulate import tabulate

# Human-readable confidence labels, shown in the output table and reused by
# the lookup log so the logged wording always matches what was displayed.
SURETY_LABELS = {
    "VERY HIGH": "Guaranteed",
    "HIGH":      "Very Likely",
    "MEDIUM":    "Likely",
    "LOW":       "Possible",
    "NONE":      "Unknown",
}


def print_output(result):
    """
    Display a result dict (from engine.find_best_match) as a clean table.
    No technical jargon — surety labels are plain English.
    """
    sep = "-" * 50
    if not result["results"]:
        print(f"\n{sep}\nNo matches found.\n{sep}")
        return

    rows = []
    for r in result["results"]:
        surety = SURETY_LABELS.get(r["confidence"], r["confidence"])
        rows.append([r["rank"], r["police_station"], r["district"], surety, r.get("distance", "N/A")])

    print(f"\n{sep}")
    print(tabulate(rows, headers=["#", "Police Station", "District", "Surety", "Distance"], tablefmt="simple"))
    print(sep)

    warning = result.get("warning")
    if warning:
        print()
        print(textwrap.fill(warning, width=72,
                            initial_indent="  [!] ", subsequent_indent="      "))
        print()
