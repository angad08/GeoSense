"""
GeoSense — output.py
---------------------
Formats and prints query results as a clean table.
"""

import pandas as pd


# Human-readable confidence labels shown in the output table
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
    sep = "-" * 40

    if not result["results"]:
        print(f"\n{sep}")
        print("No matches found.")
        print(sep)
        return

    rows = []
    for r in result["results"]:
        surety   = SURETY_LABELS.get(r["confidence"], r["confidence"])
        distance = r.get("distance", "N/A")
        rows.append({
            "Sr.No":          r["rank"],
            "Police Station": r["police_station"],
            "District":       r["district"],
            "Surety":         surety,
            "Distance":       distance,
        })

    df = pd.DataFrame(rows)

    print(f"\n{sep}")
    print(df.to_string(index=False))
    print(sep)
