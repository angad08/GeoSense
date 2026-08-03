# Setup Guide

Get GeoSense running in 5 minutes.

## Prerequisites

- Python 3.8+
- pip (comes with Python)
- Internet connection (for API key activation)

## Installation

### 1. Clone and Navigate

```bash
git clone <repository-url>
cd geosense
```

### 2. Create Virtual Environment (Recommended)

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

All dependencies are pinned to known-working versions. If you need to upgrade:
```bash
pip install --upgrade -r requirements.txt
```

### 4. Set API Keys

GeoSense needs API keys to function. Keys are read from environment variables.

#### Option A: Set for This Session Only (Quick)

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_MAPS_API_KEY="AIza..."

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:GOOGLE_MAPS_API_KEY = "AIza..."

# Windows (Command Prompt)
set ANTHROPIC_API_KEY=sk-ant-...
set GOOGLE_MAPS_API_KEY=AIza...
```

#### Option B: Create a .env File (Persistent)

Create a file named `.env` in the project root:
```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_MAPS_API_KEY=AIza...
```

That's it — it is **loaded automatically** at startup (via `python-dotenv`,
installed with `requirements.txt`). Real environment variables take
precedence over `.env` values. The AI provider itself is chosen in
`common/config.py` (`AI_PROVIDER`), not in `.env`.

`.env` is already in `.gitignore`, so your keys can't be committed by accident.

### Which API Keys Do I Need?

Keys are only needed by the rung of the lookup ladder that uses them. A
station name lookup (`--ps`) or an address the locality scan resolves needs
**no keys at all**.

| Lookup reaches... | AI provider key | Google Maps key |
|---------|----------------|-----------------|
| **Fuzzy / locality match only** | ❌ Not needed | ❌ Not needed |
| **AI district inference** (v1 & v2) | ✅ Required | ❌ Not needed |
| **Distance ranking** (v2 only) | — | ✅ Required |
| **Tests** | ❌ Not needed | ❌ Not needed |

The AI key matches your `AI_PROVIDER` setting: `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, or `GOOGLE_API_KEY`.

### Getting API Keys

#### Anthropic API Key
1. Visit [Anthropic Console](https://console.anthropic.com/)
2. Sign up or log in
3. Go to API Keys → Create Key
4. Copy and save (you can only see it once)

#### Google Maps API Key
1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the **Geocoding API**
4. Create an API key (Credentials → Create Credentials → API Key)
5. Restrict the key to the Geocoding API (security best practice)

## Verify Installation

Run the test suite — it requires **no API keys and makes no network calls**
(the paid rungs are mocked):

```bash
python -m tests.validate_test_cases
```

The last line should read:
```
SUMMARY  V1 rank-1 6/7 | V2 rank-1 6/7 | parity 7/7 | negative 1/1 | case-2 pin 1/1  => ALL GREEN
```

(6/7 is correct — case #3 is a deliberately recorded known failure, not a bug
in your setup. See the Testing section of the README.)

## Running GeoSense

### Simple Interactive Mode

```bash
python main.py
```

Follow the prompts:
```
  Address        (required) : 6-31-1, Akhila Enclave, Old Bowenpally, Secunderabad, 500011
  Known PS       (optional) :
  Known District (optional) :
```

Results (real output — this address resolves from the Excel alone, no API call):
```
--------------------------------------------------
  #  Police Station    District              Surety       Distance
---  ----------------  --------------------  -----------  ----------
  1  BOWENPALLY        MALKAJGIRI-HYDERABAD  Very Likely  N/A
--------------------------------------------------

  [LOG] Saved to 'LookupLogs': BOWENPALLY | MALKAJGIRI-HYDERABAD | DISTRICT + POLICE STATION | Very Likely
```

Distances appear when a lookup reaches the geodesic ranking rung (a district
is known or inferred and the address geocodes successfully).

### One-Shot Mode (Single Lookup)

```bash
python main.py --address "100ft Road, Madhapur" --district "Rangareddy"
```

### Use Version 1 (AI-Based)

```bash
python main.py v1 --address "Near CMH Hospital"
```

### Show Help

```bash
python main.py --help
python v1/app.py --help
python v2/app.py --help
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'pandas'`
→ Install dependencies: `pip install -r requirements.txt`

### `[ERROR] ANTHROPIC_API_KEY not set`
→ The lookup reached the AI rung without a key. Set it (or add it to `.env`):
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python main.py
```

### `[ERROR] GOOGLE_MAPS_API_KEY not set`
→ The lookup reached v2's geocoding rung. Set the key, or run `python main.py v1`.

### `ConnectionError` or `APIError`
→ Check your API keys are valid (not expired, not revoked). Geocoding errors
are caught and reported as warnings — the lookup degrades honestly instead of
crashing.

### `[WARN] Could not save coordinates`
→ The workbook is open in Excel — close it and re-run. Results are still
correct; the coordinates are simply re-geocoded next time.

### Google Maps API not working in v2
→ Verify:
1. API key is set: `echo $GOOGLE_MAPS_API_KEY` (should print your key)
2. Geocoding API is enabled in Google Cloud Console
3. API key is not rate-limited (check Cloud Console → Quotas)

### Python version mismatch
```bash
python --version  # Should be 3.8 or higher
# If not, try:
python3 --version
# Then use python3 instead of python in all commands
```

## Next Steps

- Read the [README.md](README.md) for usage examples
- Check [ARCHITECTURE.md](ARCHITECTURE.md) for how it works
- See [CONTRIBUTING.md](CONTRIBUTING.md) if you want to extend it

## Uninstall

To remove GeoSense:

```bash
# Deactivate virtual environment
deactivate

# Delete the project folder
rm -rf geosense  # macOS / Linux
rmdir /s geosense  # Windows
```

No system-wide changes were made; it's safe to remove entirely.
