# GeoSense — Police Station ⇄ District Resolver

> Give it a police station, an address, or a district — it resolves the rest. Accurately, in seconds, with the official Excel as the final word.

**Focus today:** Hyderabad & Telangana. **Direction of travel:** more regions over time — the geography lives in data, not code (see [Scope & Roadmap](#scope--roadmap)).

**In one line:** a manual, expert-dependent lookup across **751 police stations** — one that used to mean scrolling a spreadsheet or phoning the applicant back — becomes a **one-command answer in seconds**, with a confidence level and an audit trail.

| | |
|---|---|
| ⏱️ **Manual scroll → seconds** | Either direction: station→district, district→station, or a raw address→both |
| 📞 **Fewer applicant callbacks** | Messy free-text addresses resolve on the spot instead of needing a confirmation call |
| 🎯 **Zero invented stations** | The Excel is the source of truth — the AI ranks, but can never return a station that isn't in your data |
| 🔁 **Same answer every time** | Deterministic matching; the result no longer depends on which staff member ran it |
| 💸 **1 API call per lookup** | Station coordinates are geocoded once and cached in the Excel, not re-fetched every run |
| 📋 **Auditable** | Every lookup is logged with its confidence level |

---

## The Problem

Passport enrollment verification has to land each applicant's address on the **correct Police Station** — the station that physically carries out the check. That single step quietly breaks down:

- Hyderabad alone spans **hundreds of police stations** across overlapping districts, zones, and commissionerates.
- The links run **both ways and people only ever have half of it** — sometimes the police station is known but not which district it sits in; sometimes the district is known but not which station to send the case to; sometimes there's nothing but a **messy free-text address** full of door numbers, PIN codes, landmarks, and misspelled localities.
- That mapping survives in one or two experienced officers' memory, or in a spreadsheet too long to scroll.

So lookups crawl, answers differ from desk to desk, and cases get **routed to the wrong station** — meaning re-work, delays, phone calls back to the applicant, and cases stuck waiting.

## The Action — What GeoSense Does

GeoSense resolves the **District ⇄ Police Station relationship in both directions**, and fills in whatever you're missing:

| You provide | GeoSense returns | Direction |
|---|---|---|
| A **Police Station** (district unknown) | The **district** it belongs to | PS → District |
| A **District** (station unknown) | The **best-matching police stations**, ranked | District → PS |
| Only an **address** | **Both** — the district *and* the station | Address → District + PS |

It does this with a ladder of increasingly expensive steps, stopping at the first one that answers:

- **Deterministic fuzzy matching** snaps a typed or misspelled name to the real entry in your Excel.
- **Locality scanning** reads localities out of a free-text address and matches them against known stations.
- **Geographic ranking** orders the remaining candidates — by real geodesic distance (v2) or AI reasoning (v1).

And one hard rule holds across all of them:

> **The Excel is the source of truth.** The AI reasons, but it can never invent a Police Station or District — every answer must already exist in your data, or it is rejected.

A known station resolves instantly with **no AI and no cost**. The expensive rungs only run when a messy address actually needs interpreting. Every completed lookup is appended to a `LookupResults` sheet in the same workbook.

## Two Versions

The versions differ **only** in how they rank stations geographically. Everything else — matching, routing, output, logging — is shared code in `common/`.

| | **v1** | **v2** (default) |
|---|---|---|
| **Ranking** | AI estimates which station is nearest | Real geodesic distance (WGS-84, Karney's algorithm) |
| **Distance shown** | An AI estimate | A measured number in km |
| **Needs** | Any one AI provider key | Any one AI provider key + `GOOGLE_MAPS_API_KEY` |
| **Best for** | No Maps key available | Precise, reproducible ranking |

v2 is the default because a measured distance is auditable and an estimate isn't.

## See It Work

**Station known, district missing** → resolves instantly, no AI, no API cost:

```text
$ python main.py --ps "Gachibowli"

--------------------------------------------------
  #  Police Station    District              Surety      Distance
---  ----------------  --------------------  ----------  ----------
  1  GACHIBOWLI        CYBERABAD-RANGAREDDY  Guaranteed  N/A
--------------------------------------------------

  [LOG] Saved to 'LookupResults': DISTRICT | Guaranteed
```

**Only a messy address** → the locality scan reads the station area straight out of the text — still no API call:

```text
$ python main.py --address "6-31-1, Flat 101, Akhila Enclave, Old Bowenpally, Secunderabad, 500011"

--------------------------------------------------
  #  Police Station    District              Surety       Distance
---  ----------------  --------------------  -----------  ----------
  1  BOWENPALLY        MALKAJGIRI-HYDERABAD  Very Likely  N/A
--------------------------------------------------

  [LOG] Saved to 'LookupResults': DISTRICT + POLICE STATION | Very Likely
```

When the address *doesn't* name a station area, the ladder continues: the district is matched or AI-inferred, and stations are ranked by **measured geodesic distance** (`~4.2 km`-style figures in the Distance column, one Geocoding API call).

Same tool, opposite directions — and every station printed is a real row from your Excel, never invented. (Outputs above are actual runs against the Telangana dataset.)

## The Impact — Why It Matters

| Before | With GeoSense |
|---|---|
| Scroll a long spreadsheet by hand, in both directions | One answer in **seconds**, either direction |
| Ring the applicant back to re-confirm a vague address | Address resolved **on the spot**, fewer callbacks |
| Only the local expert can do it reliably | **Anyone** runs it and gets the same result |
| Answers drift between staff and shifts | **Deterministic** — the Excel decides, not memory |
| AI tools that confidently invent fake stations | **Zero hallucinated stations** — every result is real |
| Misrouted cases → re-work and delays | Right station the first time → **fewer rejections, faster turnaround** |
| No record of how a decision was made | **Built-in audit trail** of every lookup |

The point isn't the matching algorithm — it's that a slow, expert-dependent, error-prone step becomes **fast, consistent, and auditable**, in both directions.

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Choose an AI provider**

GeoSense is **provider-agnostic** — the AI rungs run behind one interface in `common/ai_client.py`, so nothing in the matching, routing, or ranking logic is tied to a vendor. Pick whichever provider you already have access to; all three are equally supported.

Set `AI_PROVIDER` in `common/config.py`, install that provider's package, and set its key. The three go together — each provider serves its own models, so the model is selected automatically to match:

| `AI_PROVIDER` | Install | Environment variable | Model used |
|---|---|---|---|
| `"anthropic"` | `pip install anthropic` | `ANTHROPIC_API_KEY` | `AI_MODEL["anthropic"]` |
| `"openai"` | `pip install openai` | `OPENAI_API_KEY` | `AI_MODEL["openai"]` |
| `"gemini"` | `pip install google-generativeai` | `GOOGLE_API_KEY` | `AI_MODEL["gemini"]` |

To switch providers, change one line in `common/config.py`:

```python
AI_PROVIDER = "anthropic"   # "anthropic" | "openai" | "gemini"
```

The model for each provider is set in the `AI_MODEL` map in the same file — edit it there to pin a different model from that provider.

**3. Set your keys**

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY / GOOGLE_API_KEY
export GOOGLE_MAPS_API_KEY=AIza...    # v2 only — geocoding, unrelated to the AI provider
```

On Windows PowerShell:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:GOOGLE_MAPS_API_KEY = "AIza..."
```

Or put the same keys in a `.env` file at the project root — it is loaded automatically (and `.gitignore` already excludes it).

> `GOOGLE_MAPS_API_KEY` is for geocoding and is **independent of your AI provider choice** — you can run Gemini for reasoning and Google Maps for distance, or OpenAI for reasoning and Google Maps for distance. They are separate services.
>
> Station-only lookups (`--ps`) resolve without any AI or Maps call and need **no key at all**.

**4. Add your Excel file**

The data file is **not included in this repo** — it is working data and may contain applicant addresses in its log sheet. Supply your own and place it at either path:

```
data/sample_police_stations.xlsx     # preferred
data/POLICE_STATION.xlsx             # fallback
```

It must contain a sheet named `PoliceStation` with `DISTRICT` and `POLICE STATION` columns. `common/config.py` resolves the path automatically — no editing needed (override with `--excel`).

---

## Usage

```bash
python main.py                      # v2 (default), interactive
python main.py v1                   # v1 explicitly
python main.py v2 --help            # flags for a version
```

**One-shot lookups:**

```bash
python main.py --ps "Gachibowli"                             # station → district
python main.py --district "Cyberabad" --address "Kondapur"   # district → station
python main.py --address "Madhapur Hyderabad"                # address → both
```

**All flags:**

| Flag | Description |
|---|---|
| `--address` | Full address string |
| `--ps` | Known police station (fuzzy matching applied) |
| `--district` | Known district (fuzzy matching applied) |
| `--excel` | Override the Excel file path |
| `--interactive` | Force interactive prompt even with flags |

> **Close the workbook in Excel before running.** v2 writes station coordinates and the lookup log back into it; Windows blocks writes to an open file. Results stay correct either way, but nothing will be saved.

---

## Station Coordinates (v2)

v2 needs a coordinate for every police station. Rather than geocoding them on every run, it stores them **in your Excel**, in two extra columns on the `PoliceStation` sheet:

| DISTRICT | POLICE STATION | LAT | LNG |
|---|---|---|---|
| ADILABAD | ADILABAD I TOWN | 19.6641 | 78.5320 |
| ADILABAD | BOATH | *(blank)* | *(blank)* |

The rule is simply:

- **Blank** → not geocoded yet → geocoded once, on demand, and written back
- **Filled** → used directly, no API call

So **adding a station to the Excel needs no rebuild step**. The first lookup that touches it geocodes it and saves the result; every lookup after that is free. Once a district is warm, a lookup makes exactly **one** API call — for the user's address.

A station that fails to geocode is left blank, **named in a warning, and never silently dropped**. It is retried next run, so a transient network problem can't become a permanent hole. If one keeps failing, its name probably needs fixing in the Excel.

**Optional:** to pay the whole geocoding cost up front instead of spreading it across your first few lookups:

```bash
python scripts/build_ps_coords.py
```

It fills every blank row in one pass and **skips rows that already have coordinates**, so it never overwrites values — including any you filled in by hand.

---

## How It Works

| Case | You know | GeoSense resolves | Method |
|---|---|---|---|
| 1 | Police Station | → District | Fuzzy match against Excel — no AI |
| 2 | District | → Police Station | Fuzzy match district → rank stations by distance |
| 3 | Only the address | → District + Police Station | Locality scan, then AI infers district → rank |
| 0 | Nothing usable | — | No result returned |

Confidence shown in the output:

| Label | Meaning |
|---|---|
| Guaranteed | Exact match on PS name |
| Very Likely | Fuzzy match on PS name |
| Likely | District matched, stations ranked |
| Possible | Inferred district and PS |
| Unknown | No confident answer |

When v2 cannot geocode the input address, it does **not** fake a ranking — it returns the district's stations unranked, marked `Possible`, and says distance ranking was unavailable.

---

## Testing

A regression harness runs the full case ladder with the paid rungs mocked, so it needs **no API keys and makes no network calls**:

```bash
python tests/validate_test_cases.py
```

It checks that v1 and v2 agree on every address-only case, that a nonsense address returns nothing rather than guessing, and that a text-matched station stays pinned at rank 1. Current baseline:

```
SUMMARY  V1 rank-1 6/7 | V2 rank-1 6/7 | parity 7/7 | negative 1/1 | case-2 pin 1/1  => ALL GREEN
```

Case 3 is a known failure, recorded deliberately rather than hidden — it names `BALANAGAR` where `SANATHNAGAR` is expected.

---

## Project Structure

```
GeoSense/
├── main.py                      # Root launcher — routes to v1 or v2
├── common/                      # Shared by both versions
│   ├── config.py                #   All settings — the main file to edit
│   ├── loader.py                #   Excel loading and standardisation
│   ├── matcher.py               #   Fuzzy matching + locality scanning
│   ├── ai_client.py             #   Provider-agnostic AI client
│   ├── api_keys.py              #   Env-var key resolution
│   ├── cli.py                   #   Argument parsing
│   ├── output.py                #   Result table formatting
│   └── lookup_log.py            #   Appends lookups to the workbook
├── v1/                          # AI-estimated ranking
│   ├── engine.py, ai_engine.py, app.py
├── v2/                          # Real geodesic distance ranking
│   ├── engine.py, ai_engine.py, app.py
│   ├── config.py                #   Shared base + v2-only settings
│   └── geopy_distance.py        #   Geocoding, distance, coordinate storage
├── scripts/
│   └── build_ps_coords.py       # Optional: bulk-fill station coordinates
├── tests/
│   └── validate_test_cases.py   # Regression harness (no network)
├── data/                        # Put your Excel here (not committed)
├── requirements.txt
└── README.md
```

---

## Configuration Reference (`common/config.py`)

| Setting | Default | Description |
|---|---|---|
| `EXCEL_FILE` | *(auto)* | Excel path, resolved from the project root |
| `SHEET_NAME` | `PoliceStation` | Sheet holding the station list |
| `COL_DISTRICT` | `DISTRICT` | Column header for district |
| `COL_PS` | `POLICE STATION` | Column header for police station |
| `COL_LAT` / `COL_LNG` | `LAT` / `LNG` | Coordinate columns (created automatically) |
| `GEOCODE_SUFFIX` | `Telangana, India` | Appended to every station geocode query |
| `FUZZY_CUTOFF` | `80` | Minimum fuzzy score (0–100) to accept a match |
| `LOCALITY_CUTOFF` | `86` | Stricter cutoff for address-locality scans |
| `TOP_N` | `3` | Number of results to return |
| `DISTANCE_WARN_KM` | `30` | v2: flag if the nearest station is farther than this |
| `AI_PROVIDER` | `anthropic` | `anthropic` \| `openai` \| `gemini` — any one is fully supported |
| `AI_MODEL` | *(per provider)* | Model map keyed by provider; edit to pin a different model |

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `[ERROR] File not found` | Put your Excel at `data/sample_police_stations.xlsx` |
| `Missing GOOGLE_MAPS_API_KEY` | Set it, or run `python main.py v1` instead |
| `[ERROR] <package> not installed` | Install the package for your chosen `AI_PROVIDER` |
| `[ERROR] <PROVIDER>_API_KEY not set` | Set the key matching `AI_PROVIDER` in `common/config.py` |
| `[WARN] Could not save coordinates` | The workbook is open in Excel — close it and re-run |
| `No module named geopy` | `pip install -r requirements.txt` |
| First lookup in a district is slow | Expected — it is geocoding that district's stations once |

---

## Scope & Roadmap

The current focus is **Hyderabad & Telangana** — the locality vocabulary, district list, and reasoning prompts are tuned for that region.

Extending it is mostly **data, not development**, because all geography lives in the Excel file:

- 🔜 **More regions** — add other states by dropping in their station list.
- 🔜 **Richer address parsing** — widen the locality vocabulary beyond Telangana terms.
- 🔜 **Batch mode** — resolve a whole sheet of addresses in one pass.
- 🔜 **API / web front-end** — offer resolution as a service.

---

## License

Released under the [MIT License](LICENSE).
