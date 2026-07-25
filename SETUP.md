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
AI_PROVIDER=anthropic
```

Then load it before running:
```bash
# Python script to load .env
python -c "from dotenv import load_dotenv; load_dotenv()"
```

Or use a manual approach:
```bash
# macOS / Linux
set -a
source .env
set +a

# Windows PowerShell
Get-Content .env | ForEach-Object {
    $key, $value = $_ -split '='
    [Environment]::SetEnvironmentVariable($key, $value)
}
```

### Which API Keys Do I Need?

| Version | Anthropic Key | Google Maps Key |
|---------|----------------|-----------------|
| **v1** | ✅ Required | ❌ Not needed |
| **v2** | ✅ Required | ✅ Required |
| **Tests** | ❌ Not needed | ❌ Not needed |

**v1 only**? Just set `ANTHROPIC_API_KEY`.  
**v2 only**? Set both keys.  
**Running tests**? No keys needed (mocked).

### Getting API Keys

#### Anthropic API Key
1. Visit [Anthropic Console](https://console.anthropic.com/)
2. Sign up or log in
3. Go to API Keys → Create Key
4. Copy and save (you can only see it once)

#### Google Maps API Key
1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable "Maps SDK for Android" (or equivalent geocoding API)
4. Create an API key (Credentials → Create Credentials → API Key)
5. Restrict to Geocoding API (Security best practice)

## Verify Installation

Run the test suite (requires no API keys):

```bash
python -m tests.validate_test_cases
```

Expected output:
```
Running GeoSense test suite...
✓ Test 1: Fuzzy match "Madhapur" → "Madhapur PS"
✓ Test 2: Locality scan "Secunderabad"
✓ Test 3: v1 ranking with AI
✓ Test 4: v2 distance calculation
...
All tests passed! ✓
```

## Running GeoSense

### Simple Interactive Mode

```bash
python main.py
```

Follow the prompts:
```
GeoSense v2 (geodesic distance)
Enter address: Madhapur
Enter district [optional]: Rangareddy
```

Results:
```
Top 3 Police Stations:
┌──────────────────┬──────────────┬──────────┬─────────┐
│ Station          │ District     │ Distance │ Surety  │
├──────────────────┼──────────────┼──────────┼─────────┤
│ Madhapur PS      │ Rangareddy   │ 0.2 km   │ High    │
│ Gachibowli PS    │ Rangareddy   │ 4.1 km   │ High    │
└──────────────────┴──────────────┴──────────┴─────────┘
```

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

### `KeyError: ANTHROPIC_API_KEY`
→ Set the key before running:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python main.py
```

### `ConnectionError` or `APIError`
→ Check your API keys are valid (not expired, not revoked)

### `Test suite takes >10 seconds`
→ Normal for first run (it mocks API responses). Subsequent runs are instant.

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
