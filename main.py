#!/usr/bin/env python3
"""
GeoSense root runner — pick a version, everything else is forwarded.

    python main.py                → v2 (default)
    python main.py v2 [args...]   → v2 (geodesic distance ranking)
    python main.py v1 [args...]   → v1 (AI ranking)

Examples:
    python main.py --address "Madhapur Hyderabad" --ps "Madhapur"
    python main.py v1 --ps "Gachibowli"
    python main.py v2 --help
"""

import sys
from pathlib import Path

# Make the project root importable even if this file is launched from
# another working directory (python path/to/GeoSense/main.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    argv = sys.argv[1:]
    version = "v2"
    if argv and argv[0].lower() in ("v1", "v2"):
        version = argv.pop(0).lower()
        sys.argv = [sys.argv[0]] + argv   # forward the rest to the version's CLI

    if version == "v1":
        from v1.app import main as run
    else:
        from v2.app import main as run
    run()


if __name__ == "__main__":
    main()
