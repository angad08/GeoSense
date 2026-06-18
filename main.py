#!/usr/bin/env python3
"""
GeoSense — Police Station Recommendation Tool
----------------------------------------------
Excel = source of truth.
AI   = reasoning only, no internet search.
Final answer always comes from the Excel file.

Usage:
    Interactive:  python main.py
    One-shot:     python main.py --address "Madhapur Hyderabad" --ps "Gachibowli"
    Help:         python main.py --help

Install for your chosen provider (set AI_PROVIDER in config.py):
    Anthropic : pip install anthropic
    OpenAI    : pip install openai
    Gemini    : pip install google-generativeai

Set the matching API key:
    export ANTHROPIC_API_KEY=sk-ant-...
    export OPENAI_API_KEY=sk-...
    export GOOGLE_API_KEY=AI...
"""

import argparse

from config    import EXCEL_FILE, AI_PROVIDER, AI_MODEL
from loader    import load_excel
from ai_engine import LazyAgent
from engine    import find_best_match
from output    import print_output
from lookup_log import log_lookup


def run_interactive(df, client, excel_path):
    """
    Prompt loop for daily use.
    Address is required. Police Station and District are optional.
    Press Enter to skip optional fields. Ctrl+C to quit.
    """
    print("\n" + "=" * 54)
    print("  GeoSense — Police Station Recommendation Tool")
    print(f"  AI: {AI_PROVIDER.upper()} — {AI_MODEL}")
    print("  Address required. Other fields optional.")
    print("  Press Enter to skip. Ctrl+C to quit.")
    print("=" * 54)

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
            result = find_best_match(address, known_ps, known_dist, df, client)
            print_output(result)
            log_lookup(result, address, known_ps, known_dist, excel_path, interactive=True)

            if input("  Another lookup? (y/n) : ").strip().lower() != "y":
                break

        except KeyboardInterrupt:
            break

    print("\n  Goodbye.\n")


def main():
    ap = argparse.ArgumentParser(
        description="GeoSense — Police Station Recommendation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--excel",       default=EXCEL_FILE, help="Path to Excel file")
    ap.add_argument("--address",     default="",         help="Full address string")
    ap.add_argument("--ps",          default="",         help="Known police station (fuzzy OK)")
    ap.add_argument("--district",    default="",         help="Known district (fuzzy OK)")
    ap.add_argument("--interactive", action="store_true", help="Force interactive prompt")
    args = ap.parse_args()

    df     = load_excel(args.excel)
    # Lazy: the AI client (and its API-key requirement) is created only if an
    # AI path is actually reached. Fuzzy-only lookups run with no key, no cost.
    client = LazyAgent()

    has_input = any([args.address, args.ps, args.district])
    if args.interactive or not has_input:
        run_interactive(df, client, args.excel)
    else:
        result = find_best_match(args.address, args.ps, args.district, df, client)
        print_output(result)
        log_lookup(result, args.address, args.ps, args.district, args.excel, interactive=False)


if __name__ == "__main__":
    main()
