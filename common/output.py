"""
GeoSense — common/output.py  (shared)
--------------------------------------
Formats and prints query results as a clean table. Shared by v1 and v2.

A result may also carry a warning or note about address precision, missing
coordinates, or shared station coordinates. These are printed under the table.

Every result also carries `state_scope` (common/state_filter.py), printed under
the table when a state was named or every state was searched. The State column
appears only for an all-states search.
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
        print(f"\n{sep}\nNo nearby stations could be ranked.\n{sep}")
        if result.get("method"):
            print(f"  Method: {result['method']}")
        if result.get("state_scope"):
            print(f"  {result['state_scope']}")
        if result.get("warning"):
            print(f"  [!] {result['warning']}")
        return

    # State is shown only when the search covered every state (no station or
    # district to go on); otherwise all rows are in the applicant's own state.
    show_state = any(r.get("state") for r in result["results"])
    headers = ["#", "Police Station", "District"] + (["State"] if show_state else []) \
              + ["Confidence", "Distance"]
    # A row can be nearer than anything in the district the user entered while
    # sitting outside it. Mark the district cell so the table does not read as
    # the district filter having failed; the legend below explains the mark.
    outside = any(r.get("outside_stated_district") for r in result["results"])
    rows = []
    for r in result["results"]:
        surety   = SURETY_LABELS.get(r["confidence"], r["confidence"])
        district = r["district"] + (" *" if r.get("outside_stated_district") else "")
        rows.append([r["rank"], r["police_station"], district]
                    + ([r.get("state", "")] if show_state else [])
                    + [surety, r.get("distance", "N/A")])

    print(f"\n{sep}")
    print(tabulate(rows, headers=headers, tablefmt="simple"))
    print(sep)
    print("  Compare the nearby candidates and their distances before selecting.")
    if outside:
        # Neutral wording: the district may have been typed by the officer
        # (Case 2) or read out of the address (Case 3b). The warning under the
        # table names which one it was.
        print("  * Outside the matched district — shown because it is nearer.")
    if result.get("method"):
        print(f"  Method: {result['method']}")

    # "all states searched" is true only when the rows carry a state; a known
    # station or district already kept the search inside one district.
    scope = result.get("state_scope")
    if scope and (show_state or "all states searched" not in scope):
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
