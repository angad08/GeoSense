# GeoSense — Address → Police Station Record Linkage

> A reference table of **~3,000 police stations** across Telangana, Andhra Pradesh and Tamil Nadu. Free-text addresses off application forms, pasted in one at a time. No consistent way to connect the two — and no measurement of how often the connection was wrong.

**Domain:** passport verification, any Indian state in the station list (currently Telangana, Andhra Pradesh, Tamil Nadu).
**Method:** data standardisation, fuzzy record linkage, geospatial enrichment, and accuracy measured against a hand-labelled set.
**Scope:** the geography lives in the data, not the code — see [Scope & Roadmap](#scope--roadmap).

**Where this started.** Cases were being routed to the wrong police station, and the assumption was that people needed to be more careful. Looking at it as data said otherwise: one reference table nobody could query consistently, addresses that never matched it cleanly, and **no metric for how often it failed**. That reframing — a data quality problem, not a diligence problem — is what the rest of this repo is.

**How it grew.**

| When | Coverage | What changed |
|---|---|---|
| June 2026 | **Hyderabad & Telangana** — 751 stations, 39 districts | First version: one state, AI-estimated ranking (now v1) |
| July–Aug 2026 | Telangana | Measured geodesic distance (v2), stored station coordinates, `(district, station)` key, regression harness |
| Sept–Oct 2026 | **+ Andhra Pradesh** (870 stations, 26 districts) and **+ Tamil Nadu** (1,379 stations, 46 districts) — **3,000 stations, 111 districts** | All region-specific code removed; states are read from the Excel's `STATE` column. TN / AP name formats, coordinate repair for hard-to-find stations |

Adding the next state is a data change, not a code change — see [Scope & Roadmap](#scope--roadmap). Details per release are in [CHANGELOG.md](CHANGELOG.md).

| Outcome | How it was achieved |
|---|---|
| ⏱️ **Manual scroll → seconds** | A 3,000-row reference table queried in either direction instead of read by eye |
| 📞 **Fewer applicant callbacks** | Messy free-text addresses standardised and matched on the spot, not sent back for confirmation |
| 📐 **A number replaced a guess** | Ranking moved from an estimate to **measured geodesic distance** — reproducible and checkable |
| 🎯 **No fabricated values** | Every returned value must already exist in the reference table, or it is rejected |
| 🔁 **Consistent by construction** | Deterministic matching — the answer no longer depends on who ran it |
| 📊 **Measured, not assumed** | A labelled test set and a regression baseline, so changes are proven not hoped (see [How It's Measured](#how-its-measured)) |
| 💸 **95–99% fewer geocoding calls** | Station coordinates resolved once and stored, not re-fetched every lookup — a median district drops from 19 calls to 1 |
| 📋 **Auditable** | Every decision logged with its confidence level |

---

## The Problem

Passport enrollment verification has to land each applicant's address on the **correct Police Station** — the station that physically carries out the check. That single step quietly breaks down:

- Hyderabad's metro districts alone hold **125 police stations** across overlapping districts, zones, and commissionerates — 751 across Telangana, and **3,000** once Andhra Pradesh and Tamil Nadu are included.
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

It works as a **cost-tiered matching pipeline** — each stage is more expensive than the last, and the pipeline stops at the first one that answers:

| Stage | Method | Cost |
|---|---|---|
| 1. **Standardise** | Trim and case-normalise the reference table on load, and drop incomplete rows | Free |
| 2. **Fuzzy match** | Token-based similarity snaps a misspelled name to its canonical row | Free |
| 3. **Locality scan** | Parses localities out of free-text and matches them against known areas, with guards against low-signal tokens and wide ties | Free |
| 4. **Geospatial rank** | Geocode the address, rank candidates by measured geodesic distance | 1 API call |
| 5. **Inference** | An LLM infers the district only when the text alone can't | 1 API call |

Stages 4 and 5 run only when the free stages cannot answer. That ordering is deliberate: **the cheapest deterministic method that can answer the question, answers it** — the expensive, non-reproducible steps are a fallback, not the default. How often each stage fires in practice is not yet measured; `LookupLogs` records the case for every lookup, so it will be.

One rule holds across every stage:

> **The reference table is the source of truth.** No stage — including the LLM — may return a Police Station or District that isn't already in the data. Anything else is rejected rather than returned.

That constraint is what makes the output safe to act on: a wrong answer is possible, but a *fabricated* one isn't. Every completed lookup is appended to a `LookupLogs` sheet with its confidence level, giving a running record of how the pipeline is performing in production.

### Same name, different district

3,000 stations, but only 2,910 distinct names — **77 names repeat across districts**, some across states. `NAWABPET` exists in Mahabubnagar and Vikarabad (Telangana) and in Nellore (Andhra Pradesh); `GUNDALA` in three Telangana districts; `SIPCOT` in six Tamil Nadu districts. These are genuinely different stations that happen to share a name, verified against the official master.

The lookup key is therefore **(district, station)**, never the station name alone. The consequences are the point:

- A name that repeats is **never resolved by spreadsheet row order** — which row Excel happens to list first has no bearing on the answer.
- Given a district, the matching record is selected.
- Given only an address, the district is often already in the text (*"…NAWABPET, POMAL, **MAHABUBNAGAR**…"*) and resolves it with no AI call, since choosing between records already in hand is a selection, not an inference. (v2 still makes one Geocoding call for the address, to order same-name matches by distance and flag one that is implausibly far.)
- Otherwise **every valid record is shown and the user picks.** Nothing is auto-selected.

This is the kind of defect that produces no error and no warning — just a quietly wrong district on a fraction of lookups, discoverable only by auditing. Treating the key as composite makes it structurally impossible.

## Two Ranking Methods, and Why v2 Is Default

The ranking stage was built twice, deliberately. Standardisation, matching, state filtering, output and logging are shared code in `common/`. The ranking method is the main difference, but not the only one. v2 also:

- checks address text matches by distance (Case 3a), ordering them nearest-first and downgrading one that is far away;
- pins a station named in the address at rank 1 when a district is given (Case 2);
- ranks the nearest stations across all states when the address names no state and the text matches nothing (Case 3n).

v1 does none of these.

| | **v1** | **v2** (default) |
|---|---|---|
| **Ranking** | Model estimates which station is nearest | Measured geodesic distance (WGS-84, Karney's algorithm) |
| **Distance shown** | An estimate | A number in km, reproducible from the coordinates |
| **Re-run on the same input** | May vary | Identical every time |
| **Needs** | Any one AI provider key | Any one AI provider key + `GOOGLE_MAPS_API_KEY` |

**v2 is the default on properties that can be checked without a benchmark:** its distance is reproducible from the stored coordinates, explainable after the fact, identical on every re-run of the same input, and free to recompute once coordinates are saved. An estimate offers none of those regardless of how accurate it is. v1 remains the fallback for when no Maps key is available.

**Which one ranks *better* is not yet measured, and this repo does not claim it.** The regression harness runs with the paid stages mocked, and on its current cases the free text scan resolves every address before ranking is reached — so neither ranking method is exercised (see [How It's Measured](#how-its-measured)). What the harness does establish is that the shared layer really is shared, which is the precondition for a fair comparison later. A fair comparison still has to account for v2's extra steps listed above, not only its ranking.

The honest test needs production data, not fixtures — the same addresses through both versions with keys live, scored against the hand-labelled `ACTUAL PS KNOWN` column that `LookupLogs` is accumulating. Until there are enough rows for that, "v2 is more accurate" would be an assumption wearing a number.

## See It Work

**Station known, district missing** → resolves instantly, no AI, no API cost:

```text
$ python main.py --ps "Gachibowli"

--------------------------------------------------
  #  Police Station    District              Confidence  Distance
---  ----------------  --------------------  ----------  ----------
  1  GACHIBOWLI        CYBERABAD-RANGAREDDY  Guaranteed  N/A
--------------------------------------------------

  [LOG] Saved to 'LookupLogs': GACHIBOWLI | CYBERABAD-RANGAREDDY | DISTRICT | Guaranteed
```

**Only a messy address** → the locality scan reads the station area straight out of the text — no AI call. v2 then makes one Geocoding call for the address to check the match by distance; `N/A` below means that check was unavailable, and the text match stands:

```text
$ python main.py --address "6-31-1, Flat 101, Akhila Enclave, Old Bowenpally, Secunderabad, 500011"

--------------------------------------------------
  #  Police Station    District              Confidence   Distance
---  ----------------  --------------------  -----------  ----------
  1  BOWENPALLY        MALKAJGIRI-HYDERABAD  Very Likely  N/A
--------------------------------------------------

  [LOG] Saved to 'LookupLogs': BOWENPALLY | MALKAJGIRI-HYDERABAD | DISTRICT + POLICE STATION | Very Likely
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
| Misrouted cases → re-work and delays | Same input, same station — and a misroute becomes **traceable** instead of invisible |
| No record of how a decision was made | **Built-in audit trail** of every lookup |

The point isn't the matching algorithm — it's that a slow, expert-dependent, unmeasured step becomes **fast, consistent, and quantified**.

---

## How It's Measured

A matcher that can't be evaluated is a guess with extra steps. Two things make this one checkable:

**1. A hand-labelled ground-truth set.** Real addresses paired with the station a human confirmed was correct — `ACTUAL` beside `PREDICTED`, with a match rate computed across the set. This is what turns "it seems to work" into a number, and it's the artifact that drives every decision below. *(Kept out of this repo: it contains real applicant addresses.)*

**2. A regression harness that runs with no API keys and no network.** The paid stages are mocked, so the deterministic logic can be re-tested on every change for free:

```
V1 rank-1 6/7 | V2 rank-1 6/7 | parity 7/7 | negative 1/1 | case-2 pin 1/1 | duplicates 5/5  => ALL GREEN
```

What each figure is actually checking:

| Metric | What it proves |
|---|---|
| **rank-1 6/7** | The **locality scan** puts the correct station first on 6 of 7 address-only cases |
| **parity 7/7** | v1 and v2 return identical results on every case — the shared layer really is shared |
| **negative 1/1** | A nonsense address returns **nothing** rather than a confident wrong answer |
| **case-2 pin 1/1** | A station named in the text stays rank 1 and isn't displaced by distance — checked against canned distances, so it proves the composition, not the distances |
| **duplicates 5/5** | A station name shared by several districts resolves to the right record — asserting the exact `(station, district)` pairs returned, not merely that the lookup ran |

**What these numbers do not cover.** Every current case is answered by the free text scan before ranking is reached, so neither ranking method runs — the mock is never even called. That makes 6/7 a measure of `common/matcher.py`, not of v1 versus v2. Comparing the two ranking methods needs live keys and labelled production rows, which `LookupLogs` is collecting; it is not something this harness can answer, and the harness should not be read as answering it.

Two deliberate choices worth calling out:

- **The failing case is recorded, not hidden.** Case 3 returns `BALANAGAR` where `SANATHNAGAR` is expected. It's in the harness as a known failure with the expected value written down — so if a future change happens to fix it, that shows up as a result rather than going unnoticed.
- **A negative test carries as much weight as a positive one.** Silent false positives are the expensive failure mode here: a wrong station routes a case to the wrong desk and nobody notices for days. Returning nothing is recoverable; returning something plausible and wrong is not.

The duplicate-name checks exist for the same reason. Two of the seven address cases involve a station name that repeats across districts, and both happened to land on the right district anyway — purely because of where those rows sit in the spreadsheet. Tests that assert the exact `(station, district)` pair, rather than the station name alone, are what stop that from passing for the wrong reason.

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

`common/config.py` resolves the path automatically — no editing needed (override with `--excel`). The workbook needs two sheets:

**`PoliceStation`** — the reference table.

| Column | Required | Notes |
|---|---|---|
| `DISTRICT` | ✅ | |
| `POLICE STATION` | ✅ | May repeat across districts — see [Same name, different district](#same-name-different-district) |
| `STATE` | Recommended | Used to search only the state an address names (otherwise all states), and to build each station's geocode query. A station with a blank `STATE` is never geocoded, and a missing column means every state is always searched |
| `LAT` / `LNG` | — | Station coordinates, filled by `scripts/build_ps_coords.py` |

**`LookupLogs`** — the audit log, written one row per completed lookup.

This sheet is **shared**: the script writes some columns, you fill in the rest by hand, and they sit interleaved. Writes are therefore located **by header text**, never by position — so a missing or renamed header stops the run with a clear message rather than writing into the wrong column.

| Column | Written by |
|---|---|
| `ADDRESS`, `PREDICTED PS`, `PREDICTED DISTRICT`, `RESULT LOOKUP`, `RESULT MATCH` | the script |
| `FILE NO`, `ACTUAL PS KNOWN`, `STATUS`, `MATCH` | you — never touched by the script |

`PREDICTED PS` holds the station name only, so it stays directly comparable to your hand-entered `ACTUAL PS KNOWN`; the district goes in its own `PREDICTED DISTRICT` column. If you decline to pick a result, the row is still logged with those cells left blank for you to complete. Anything to the right of the table is left alone, and if the sheet uses an Excel Table its range is extended so new rows stay inside it.

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

> **Close the workbook in Excel before running.** Lookups write the lookup log back into it, and `scripts/build_ps_coords.py` writes station coordinates; Windows blocks writes to an open file. Results stay correct either way, but nothing will be saved.

---

## Station Coordinates (v2)

v2 needs a coordinate for every police station. Rather than geocoding them on every run, it stores them **in your Excel**, in two extra columns on the `PoliceStation` sheet:

| DISTRICT | POLICE STATION | LAT | LNG |
|---|---|---|---|
| ADILABAD | ADILABAD I TOWN | 19.6765668 | 78.5320841 |
| ADILABAD | *(a newly added station)* | *(blank)* | *(blank)* |

The rule is simply:

- **Blank** → not geocoded yet → filled by `build_ps_coords.py` (below)
- **Filled** → used directly, no API call

Lookups never geocode stations themselves. A lookup that reaches the ranking stage makes exactly **one Geocoding call** — for the user's address. (An address that also needs its district inferred adds one AI call on top; a lookup answered by the free stages makes neither.) A station with blank coordinates can still be matched by name, but is left out of distance ranking and named in a note.

A station that fails to geocode is left blank, **named in a warning, and never silently dropped**. It is retried on the next build run. If one keeps failing, see *Stations Google cannot find by their name* below.

**After adding stations to the Excel**, fill their coordinates:

```bash
python scripts/build_ps_coords.py
```

It fills every blank row in one pass and **skips rows that already have coordinates**, so it never overwrites values — including any you filled in by hand.

**Stations sharing one point.** For small stations Google sometimes returns a bigger police building nearby, so several differently named stations end up on one coordinate and their distances are wrong. To move them to the village or town each is named after:

```bash
python scripts/build_ps_coords.py --restack --limit 20   # preview 20, nothing written
python scripts/build_ps_coords.py --restack --fix        # all of them, saved
```

One Geocoding call per station. A move is saved only if Google returns a village / town whose name matches the station, in the row's state, near the rest of its district, and not on another station's point; otherwise the station keeps its current point. Back up the Excel and close it first.

**Stations Google cannot find by their name.** Some official names are abbreviated, spelled differently from Google, or too generic to search (`T.V.NALLUR`, `CHENAM`, `BAZAAR`). For these, add a row to `data/station_search_names.csv`, then rerun `build_ps_coords.py`:

| DISTRICT | POLICE STATION | SEARCH NAME |
|---|---|---|
| VILUPPURAM | T.V.NALLUR | THIRUVENNAINALLUR |
| TIRUVANNAMALAI | CHENAM | CHENGAM |
| RAMANATHAPURAM | BAZAAR | RAMANATHAPURAM BAZAAR |

- DISTRICT and POLICE STATION must match the Excel row exactly; SEARCH NAME is what Google is asked for.
- Only the geocode search uses it. The Excel name is never changed, and normal lookups never read this file.
- Every safety check (state, district, same point) still applies to the result.
- Only add a row for a station that failed. A row that no longer matches the Excel (station renamed) is ignored.

It is mostly idle: once a station has coordinates it is never searched again. Its use is recovery — if coordinates are ever wiped (OneDrive rollback, `--audit --fix`), a rerun finds these stations again without redoing the research.

If Google cannot find a station under any name, type its verified LAT / LNG into the Excel by hand; the script keeps hand-entered values.

---

## How It Works

| Case | You know | GeoSense resolves | Method |
|---|---|---|---|
| 1 | Police Station | → District | Fuzzy match against Excel — no AI. If the name exists in several districts, a supplied district selects one; otherwise every valid record is returned to choose from |
| 2 | District | → Police Station | Fuzzy match district → rank stations by distance |
| 3 | Only the address | → District + Police Station | Locality scan, then AI infers district → rank |
| 0 | Nothing usable | — | No result returned |

Confidence shown in the output:

| Label | When it is used |
|---|---|
| Guaranteed | A station name you typed matched a row exactly |
| Very Likely | A typed name matched closely, **or** the address clearly named a station area, **or** the top result of a ranked district |
| Likely | A lower-ranked candidate, a typed name that exists in **several districts** (choose one), or a district the model inferred |
| Possible | Distance ranking was unavailable, or a lower-ranked candidate from an inferred district |
| Unknown | No confident answer — nothing is returned |

When v2 cannot geocode the input address, it does **not** fake a ranking — it returns the district's stations unranked, marked `Possible`, and says distance ranking was unavailable.

---

## Testing

A regression harness runs the full case ladder with the paid rungs mocked, so it needs **no API keys and makes no network calls**:

```bash
python tests/validate_test_cases.py
```

Expected result and what each metric means: see [How It's Measured](#how-its-measured).

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
│   └── station_search_names.csv #   Search names for hard-to-find stations (committed)
├── requirements.txt
├── README.md
└── CHANGELOG.md                 # What changed, including Excel coordinate fixes
```

---

## Configuration Reference (`common/config.py`)

| Setting | Default | Description |
|---|---|---|
| `EXCEL_FILE` | *(auto)* | Excel path, resolved from the project root |
| `SHEET_NAME` | `PoliceStation` | Sheet holding the station list |
| `LOG_SHEET_NAME` | `LookupLogs` | Sheet the audit log is appended to |
| `LOG_WRITE_COLS` | *(5 headers)* | Columns the script writes, matched by header text |
| `LOG_MANUAL_COLS` | *(4 headers)* | Hand-maintained columns — never written or cleared |
| `COL_DISTRICT` | `DISTRICT` | Column header for district |
| `COL_PS` | `POLICE STATION` | Column header for police station |
| `COL_LAT` / `COL_LNG` | `LAT` / `LNG` | Coordinate columns (created automatically) |
| `COL_STATE` | `STATE` | Per-row state; station query is `{PS} Police Station, {DISTRICT}, {STATE}, India`. Blank → station skipped, never defaulted |
| `SEARCH_ALIAS_FILE` | `data/station_search_names.csv` | Search names for stations Google cannot find by their Excel name — see [Station Coordinates](#station-coordinates-v2) |
| `COORD_LAT_MIN/MAX`, `COORD_LNG_MIN/MAX` | `6.0–37.6`, `68.0–97.5` | India's outer box; a geocoded station outside it is rejected, not written |
| `SIBLING_MAX_KM` / `SIBLING_MIN_COUNT` | `35` / `3` | A geocoded station more than 35 km from every other station of its district **and** placed by Google in another district is a same-name village elsewhere — rejected. `python scripts/build_ps_coords.py --audit [--fix]` re-checks stored coordinates the same way |
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
| `[WARN] Could not save coordinates` | The workbook is open in Excel — close it and re-run `scripts/build_ps_coords.py` |
| `Sheet 'LookupLogs' not found` | Add the sheet, or point `LOG_SHEET_NAME` at the one you use |
| `missing expected column(s): …` | Add the named header to `LookupLogs`. Nothing is written until it exists — deliberately, so a value never lands in the wrong column |
| `No module named geopy` | `pip install -r requirements.txt` |
| Stations left out of distance ranking | They have no coordinates yet. Lookups never geocode stations — run `python scripts/build_ps_coords.py` |

---

## Scope & Roadmap

Nothing in the code is tied to a region. The state list, the state words ignored in addresses, the AI prompts' region and district list, and the geocode sanity check (the result must lie in the row's own STATE) are all read from the STATE column of the Excel.

Extending it is mostly **data, not development**, because all geography lives in the Excel file:

- ✅ **More regions** — add any state by adding its rows (with STATE filled) to the station list. No code or config change.
- ✅ **Richer address parsing** — station-code prefixes (Chennai's `K-4 ANNANAGAR`), joined/split words (ANNA NAGAR vs ANNANAGAR), `P.S` suffixes, all-women stations in either format (`ALL WOMEN PS BODI` = `BODI AWPS`), and names with a bracket or `U/G` (`MYDUKUR U/G` matches "MYDUKUR") — the short form is used only when no other station shares it, so `SIRPUR(U)` never answers for SIRPUR TOWN.
- ✅ **Relisted stations** — a station listed under two districts at the same point (e.g. Tamil Nadu's VELLORE / RANIPET rows after the 2019 split) is shown once, naming both districts. The sheet keeps both rows.
- 🔜 **Batch mode** — resolve a whole sheet of addresses in one pass.
- 🔜 **API / web front-end** — offer resolution as a service.

---

## License

Released under the [MIT License](LICENSE).
