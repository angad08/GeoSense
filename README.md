# GeoSense — Police Station Recommendation Tool

Recommends the correct Police Station for passport enrollment verification in Hyderabad and Telangana.

Excel is the source of truth. The AI handles geographic reasoning only — it cannot invent Police Station or District names. Every result is validated against the Excel before it is shown.

---

## Project Structure

```
GeoSense/
├── main.py         # CLI entry point and interactive prompt loop
├── config.py       # All settings — the only file you need to edit
├── loader.py       # Excel loading and standardisation
├── matcher.py      # Fuzzy matching for PS and District lookups
├── ai_engine.py    # AI client setup, call wrapper, reasoning prompts
├── engine.py       # Main decision logic (Cases 1 / 2 / 3)
├── output.py       # Table formatting and surety labels
├── lookup_log.py   # Appends completed lookups to the workbook
├── data/           # Place POLICE_STATION.xlsx here (not committed)
├── requirements.txt
└── README.md
```

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

Install only the AI provider you plan to use:

```bash
pip install anthropic          # for Anthropic (default)
pip install openai             # for OpenAI
pip install google-generativeai  # for Gemini
```

**2. Set your API key**

```bash
# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
export OPENAI_API_KEY=sk-...

# Gemini
export GOOGLE_API_KEY=AI...
```

**3. Add your Excel file**

The data file is **not included** in this repo. Supply your own and place it at:

```
GeoSense/data/POLICE_STATION.xlsx
```

It must contain a sheet named `PoliceStation` with `DISTRICT` and `POLICE STATION` columns. `config.py` resolves this path automatically relative to itself — no editing needed (override with `--excel` if you keep it elsewhere).

**4. Choose your AI provider in `config.py`**

```python
AI_PROVIDER = "anthropic"   # "anthropic" | "openai" | "gemini"
```

---

## Usage

**Interactive mode** (default when no flags are given):

```bash
python main.py
```

**One-shot mode:**

```bash
python main.py --address "Madhapur Hyderabad"
python main.py --address "Kondapur" --district "Cyberabad"
python main.py --ps "Gachibowli"
```

**All flags:**

| Flag | Description |
|---|---|
| `--address` | Full address string |
| `--ps` | Known police station (fuzzy matching applied) |
| `--district` | Known district (fuzzy matching applied) |
| `--excel` | Override Excel file path |
| `--interactive` | Force interactive prompt even with flags |

---

## How It Works

| Case | Input | Method |
|---|---|---|
| 1 | Police Station known | Fuzzy match against Excel — no AI used |
| 2 | District known | Fuzzy match district → AI ranks PS by address |
| 3 | Address only | AI infers district → AI ranks PS |
| 0 | Nothing | No result returned |

The confidence level shown in output:

| Label | Meaning |
|---|---|
| Guaranteed | Exact match on PS name |
| Very Likely | Fuzzy match on PS name |
| Likely | District matched, AI ranked |
| Possible | AI-inferred district and PS |

---

## Configuration Reference (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `EXCEL_FILE` | *(path)* | Path to the Police Station Excel file |
| `SHEET_NAME` | `PoliceStation` | Sheet name in Excel |
| `COL_DISTRICT` | `DISTRICT` | Column header for district |
| `COL_PS` | `POLICE STATION` | Column header for police station |
| `FUZZY_CUTOFF` | `80` | Minimum fuzzy score (0–100) to accept a match |
| `TOP_N` | `3` | Number of results to return |
| `AI_PROVIDER` | `anthropic` | AI provider: `anthropic`, `openai`, `gemini` |
| `AI_MODEL` | *(auto)* | Model selected automatically from `AI_PROVIDER` |
