# GeoSense — Police Station Recommendation Tool

> Find the correct Police Station for any address in seconds — accurately, repeatably, and without guesswork.

**Coverage today:** Hyderabad & Telangana. **By design:** any region — just swap in its Excel of districts and police stations (see [Scope & Roadmap](#scope--roadmap)).

---

## The Problem

Passport enrollment verification requires assigning each applicant's address to the **correct Police Station** — the one that will actually carry out the physical verification. In practice this is harder than it sounds:

- A single city like Hyderabad has **hundreds of police stations** spread across overlapping districts, zones, and commissionerates.
- Addresses arrive as **messy free text** — door numbers, flat numbers, PIN codes, landmarks, misspelled localities, mixed languages, no district named.
- The mapping lives in the heads of a few experienced officers, or buried in a spreadsheet nobody wants to scroll through.

The result: **slow lookups, inconsistent answers, and verification sent to the wrong station** — which means re-work, delays, and applicants caught in the middle.

## Why It Matters — The Impact

| Before | With GeoSense |
|---|---|
| Manual scan of a long spreadsheet per address | Answer in **seconds**, typed or piped |
| Depends on one expert's local knowledge | **Anyone** can run it and get the same answer |
| Inconsistent results between staff | **Deterministic** — Excel is the single source of truth |
| Misrouted verifications, re-work, delays | Right station the first time → **fewer rejections, faster turnaround** |

GeoSense turns a slow, expert-dependent, error-prone step into a **fast, consistent, auditable** one — and every lookup is logged back into the workbook for traceability.

## The Solution

GeoSense pairs **deterministic fuzzy matching** with **AI geographic reasoning**, with a strict rule:

> **Excel is the source of truth. The AI reasons, but it can never invent a Police Station or District name. Every result is validated against the Excel before it is shown.**

So you get the speed and flexibility of AI for messy addresses, with **zero hallucinated stations** — the final answer always exists in your official data.

- **Knows the station?** → instant fuzzy match, **no AI, no cost.**
- **Knows the district?** → AI ranks the stations within it by the address.
- **Only an address?** → AI infers the district from locality names, then ranks the stations — all constrained to your Excel.

---

## Scope & Roadmap

**Right now**, GeoSense ships tuned for **Hyderabad & Telangana** — the locality vocabulary, district list, and prompts reflect that region.

It is **built to extend**. The geography lives entirely in the Excel file, not the code, so adding a new region is mostly **data, not development**:

- 🔜 **Other states / cities** — drop in a new `POLICE_STATION.xlsx` with that region's districts and stations.
- 🔜 **Richer address parsing** — broaden the locality vocabulary beyond Telangana terms.
- 🔜 **Batch mode** — process a full sheet of addresses at once.
- 🔜 **API / web front-end** — expose lookups as a service.

This is an **actively improving** project; the sections below describe the current, working tool.

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
pip install anthropic            # for Anthropic (default)
pip install openai               # for OpenAI
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

> Station-only lookups (`--ps`) never call the AI and need **no key**.

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

Every completed lookup is appended to a `LookupResults` sheet inside the same workbook, giving you a built-in audit trail.

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

---

## License

Released under the [MIT License](LICENSE).
