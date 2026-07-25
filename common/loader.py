"""
GeoSense — common/loader.py  (shared)
--------------------------------------
Reads the Excel file and returns a clean, standardised DataFrame.
Shared by v1 and v2 — behaviour is identical in both.
"""

import os
import sys

import pandas as pd

from common.config import SHEET_NAME, COL_DISTRICT, COL_PS


def load_excel(file_path):
    """
    Read the Excel file and return a clean DataFrame.
    Exits the program if the file cannot be loaded.

    Standardisation applied:
      - Column names stripped and uppercased
      - DISTRICT and POLICE STATION values stripped, uppercased, nulls dropped
    """
    if not os.path.exists(str(file_path)):
        print(f"\n[ERROR] File not found: {file_path}")
        print("        Set EXCEL_FILE in common/config.py, or pass --excel flag.\n")
        sys.exit(1)

    try:
        df = pd.read_excel(file_path, sheet_name=SHEET_NAME)
    except Exception as err:
        print(f"\n[ERROR] Could not read Excel: {err}\n")
        sys.exit(1)

    df.columns       = [c.strip().upper() for c in df.columns]
    df               = df[[COL_DISTRICT, COL_PS]].dropna()
    df[COL_DISTRICT] = df[COL_DISTRICT].str.strip().str.upper()
    df[COL_PS]       = df[COL_PS].str.strip().str.upper()

    return df.reset_index(drop=True)
