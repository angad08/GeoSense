# Quick Start (2 minutes)

**Just want to run it?** Start here.

## Install

```bash
pip install -r requirements.txt
```

## Add your Excel file

The station data is not included in this repo. Place your workbook at:

```
data/sample_police_stations.xlsx
```

It needs a `PoliceStation` sheet with `DISTRICT` and `POLICE STATION` columns.

## Try it — no API keys needed

Station and locality lookups resolve entirely from the Excel:

```bash
python main.py --ps "Gachibowli"
```

```text
--------------------------------------------------
  #  Police Station    District              Surety      Distance
---  ----------------  --------------------  ----------  ----------
  1  GACHIBOWLI        CYBERABAD-RANGAREDDY  Guaranteed  N/A
--------------------------------------------------
```

The regression tests also need no keys:

```bash
python -m tests.validate_test_cases
```

## Set API keys (for the paid rungs)

Only needed when a lookup actually reaches geocoding or AI — messy addresses
that the text scan can't resolve:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."          # AI district inference
export GOOGLE_MAPS_API_KEY="AIza..."           # v2 distance ranking
```

Or put the same lines in a `.env` file at the project root — it's loaded
automatically.

> Don't have keys? Get them:
> - Anthropic: https://console.anthropic.com/
> - Google Maps: https://console.cloud.google.com/ → enable **Geocoding API**

## Run

```bash
python main.py                                  # v2 (default), interactive
python main.py --address "Madhapur Hyderabad"   # address → district + station
python main.py v1                               # v1 (AI-estimated ranking)
```

## v1 vs v2

Both share the same matching and routing — they differ only in how stations
are ranked geographically:

| | v1 | v2 (default) |
|---------|---------|---------------|
| **Ranking** | AI estimates distances | Real geodesic distance (WGS-84) |
| **Distance shown** | An AI guess | A measured number in km |
| **Needs** | AI provider key | AI provider key + Google Maps key |

v2 is the default because a measured distance is auditable and an estimate
isn't.

## Need Help?

- Setup issues? → [SETUP.md](SETUP.md)
- How it works? → [ARCHITECTURE.md](ARCHITECTURE.md)
- Full docs? → [README.md](README.md)
