"""
GeoSense — common/cli.py  (shared)
-----------------------------------
The command-line shell both versions share: argument parsing, the interactive
prompt loop, and the one-shot path. A version's main.py supplies only what
actually differs — its find_best_match and its banner lines.
"""

import argparse

from common.config import EXCEL_FILE
from common.loader import load_excel
from common.ai_client import LazyAgent
from common.output import print_output
from common.lookup_log import log_lookup


def run_interactive(df, ai_client, excel_path, find_best_match, banner_lines):
    """
    Prompt loop for daily use.
    Address is required. Police Station and District are optional.
    Press Enter to skip optional fields. Ctrl+C to quit.
    """
    print("\n" + "=" * 58)
    for line in banner_lines:
        print(f"  {line}")
    print("=" * 58)

    while True:
        try:
            print()
            address = ""
            while not address:
                address = input("  Address        (required) : ").strip()
                if not address:
                    print("  Address cannot be empty.")

            known_ps   = input("  Known PS       (optional) : ").strip()
            known_dist = input("  Known District (optional) : ").strip()

            print()
            result = find_best_match(address, known_ps, known_dist, df, ai_client)
            print_output(result)
            log_lookup(result, address, known_ps, known_dist, excel_path, interactive=True)

            if input("  Another lookup? (y/n) : ").strip().lower() != "y":
                break

        except KeyboardInterrupt:
            break

    print("\n  Goodbye.\n")


def run_cli(find_best_match, banner_lines, epilog=""):
    """
    Parse arguments, load the Excel, then route to interactive or one-shot.
    """
    ap = argparse.ArgumentParser(
        description="GeoSense — Police Station Recommendation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    ap.add_argument("--excel",       default=str(EXCEL_FILE), help="Path to Excel file")
    ap.add_argument("--address",     default="",              help="Full address string")
    ap.add_argument("--ps",          default="",              help="Known police station (fuzzy OK)")
    ap.add_argument("--district",    default="",              help="Known district (fuzzy OK)")
    ap.add_argument("--interactive", action="store_true",     help="Force interactive prompt")
    args = ap.parse_args()

    df = load_excel(args.excel)

    # Lazy: the AI client (and its API-key requirement) is created only if an
    # AI rung is actually reached. Fuzzy- and locality-only lookups run with no
    # AI key and no cost. (v2's Maps client defers the same way — see
    # v2/geopy_distance._client().)
    ai_client = LazyAgent()

    has_input = any([args.address, args.ps, args.district])
    if args.interactive or not has_input:
        run_interactive(df, ai_client, args.excel, find_best_match, banner_lines)
    else:
        result = find_best_match(args.address, args.ps, args.district, df, ai_client)
        print_output(result)
        log_lookup(result, args.address, args.ps, args.district, args.excel, interactive=False)
