# Quick Start (2 minutes)

**Just want to run it?** Start here.

## Install

```bash
pip install -r requirements.txt
```

## Set API Keys

```bash
export ANTHROPIC_API_KEY="sk-ant-..."          # Required
export GOOGLE_MAPS_API_KEY="AIza..."           # Only for v2
```

> Don't have keys? Get them:
> - Anthropic: https://console.anthropic.com/keys
> - Google Maps: https://console.cloud.google.com/ → Geocoding API

## Run

```bash
# Interactive mode (asks for input)
python main.py

# Single lookup
python main.py --address "Madhapur" --district "Rangareddy"

# Use v1 (AI-based, slower but smarter)
python main.py v1

# Run tests (no API keys needed)
python -m tests.validate_test_cases
```

## What You'll See

```
GeoSense v2 — Geodesic Distance Ranking
Enter address: Madhapur
Enter district [optional]: Rangareddy

Top 3 Police Stations:
┌──────────────────┬──────────────┬──────────┬─────────┐
│ Station          │ District     │ Distance │ Surety  │
├──────────────────┼──────────────┼──────────┼─────────┤
│ Madhapur PS      │ Rangareddy   │ 0.2 km   │ High    │
│ Gachibowli PS    │ Rangareddy   │ 4.1 km   │ High    │
│ Secunderabad PS  │ Rangareddy   │ 12.3 km  │ Medium  │
└──────────────────┴──────────────┴──────────┴─────────┘
```

## v1 vs v2

| Feature | v1 (AI) | v2 (Distance) |
|---------|---------|---------------|
| **Speed** | 2-3 sec | <500ms |
| **Accuracy** | Good | Better |
| **Cost** | Higher | Lower |
| **Run** | `python main.py v1` | `python main.py` |

## Need Help?

- Setup issues? → [SETUP.md](SETUP.md)
- How it works? → [ARCHITECTURE.md](ARCHITECTURE.md)
- Full docs? → [README.md](README.md)
