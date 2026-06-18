# GeoSense — Police Station ⇄ District Resolver

> Give it a police station, an address, or a district — it resolves the rest. Accurately, in seconds, with the official Excel as the final word.

**Focus today:** Hyderabad & Telangana. **Direction of travel:** more regions over time — the geography lives in data, not code (see [Scope & Roadmap](#scope--roadmap)).

---

## The Problem

Passport enrollment verification has to land each applicant's address on the **correct Police Station** — the station that physically carries out the check. That single step quietly breaks down:

- Hyderabad alone spans **hundreds of police stations** across overlapping districts, zones, and commissionerates.
- The links run **both ways and people only ever have half of it** — sometimes the police station is known but not which district it sits in; sometimes the district is known but not which station to send the case to; sometimes there's nothing but a **messy free-text address** full of door numbers, PIN codes, landmarks, and misspelled localities.
- That mapping survives in one or two experienced officers' memory, or in a spreadsheet too long to scroll.

So lookups crawl, answers differ from desk to desk, and cases get **routed to the wrong station** — meaning re-work, delays, and applicants stuck waiting.

## The Action — What GeoSense Does

GeoSense resolves the **District ⇄ Police Station relationship in both directions**, and fills in whatever you're missing:

| You provide | GeoSense returns | Direction |
|---|---|---|
| A **Police Station** (district unknown) | The **district** it belongs to | PS → District |
| A **District** (station unknown) | The **best-matching police stations**, ranked | District → PS |
| Only an **address** | **Both** — the district *and* the station | Address → District + PS |

It does this by pairing two engines, and keeping one hard rule between them:

- **Deterministic fuzzy matching** snaps a typed or misspelled name to the real entry in your Excel.
- **AI geographic reasoning** reads a messy address, infers the district from locality names, and ranks the stations within it.
- **The rule:** the **Excel is the source of truth.** The AI reasons, but it can never invent a Police Station or District — every answer it returns must already exist in your data, or it's rejected.

A known station resolves instantly with **no AI and no cost**; the AI only steps in when an address actually needs interpreting. Every completed lookup is written back into a `LookupResults` sheet in the same workbook.

## The Impact — Why It Matters

| Before | With GeoSense |
|---|---|
| Scroll a long spreadsheet, both directions, by hand | One answer in **seconds**, either direction |
| Only the local expert can do it reliably | **Anyone** runs it and gets the same result |
| Answers drift between staff and shifts | **Deterministic** — the Excel decides, not memory |
| AI tools that confidently invent fake stations | **Zero hallucinated stations** — every result is real |
| Misrouted cases → re-work and delays | Right station the first time → **fewer rejections, faster turnaround** |
| No record of how a decision was made | **Built-in audit trail** of every lookup |

The point isn't the matching algorithm — it's that a slow, expert-dependent, error-prone step becomes **fast, consistent, and auditable**, in both directions.

---

## Scope & Roadmap

The current focus is **Hyderabad & Telangana** — the locality vocabulary, district list, and reasoning prompts are tuned for that region.

Extending it is mostly **data, not development**, because all geography lives in the Excel file:

- 🔜 **More regions** — add other states and cities by dropping in their `POLICE_STATION.xlsx`.
- 🔜 **Richer address parsing** — widen the locality vocabulary beyond Telangana terms.
- 🔜 **Batch mode** — resolve a whole sheet of addresses in one pass.
- 🔜 **API / web front-end** — offer resolution as a service.

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

Install only the AI provider you plan to run:

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

> Station-only lookups (`--ps`) resolve without the AI and need **no key**.

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
python main.py --ps "Gachibowli"                          # station → district
python main.py --district "Cyberabad" --address "Kondapur" # district → station
python main.py --address "Madhapur Hyderabad"             # address → both
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

| Case | You know | GeoSense resolves | Method |
|---|---|---|---|
| 1 | Police Station | → District | Fuzzy match against Excel — no AI |
| 2 | District | → Police Station | Fuzzy match district → AI ranks stations by address |
| 3 | Only the address | → District + Police Station | AI infers district → AI ranks stations |
| 0 | Nothing usable | — | No result returned |

The confidence level shown in output:

| Label | Meaning |
|---|---|
| Guaranteed | Exact match on PS name |
| Very Likely | Fuzzy match on PS name |
| Likely | District matched, AI ranked |
| Possible | AI-inferred district and PS |

Every completed lookup is appended to a `LookupResults` sheet inside the same workbook — a built-in audit trail.

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
