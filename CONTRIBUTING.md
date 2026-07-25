# Contributing to GeoSense

Thank you for your interest in improving GeoSense! This document outlines the development workflow.

## Setup for Development

```bash
# Clone repo
git clone <repo>
cd geosense

# Create virtual environment
python -m venv venv
source venv/bin/activate          # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set test environment variables (no real API calls)
export ANTHROPIC_API_KEY="test-key"
export GOOGLE_MAPS_API_KEY="test-key"
```

## Running Tests

```bash
# Full regression suite (no network calls)
python -m tests.validate_test_cases

# Test a specific version
python -m tests.validate_test_cases --version v2

# With verbose output
python -m tests.validate_test_cases --verbose
```

## Making Changes

### Code Organization
- **`common/`**: Shared logic (text matching, config, I/O) — changes here affect both v1 and v2
- **`v1/`**: AI-based ranking only — isolated changes
- **`v2/`**: Geodesic distance + geocoding — isolated changes

### Guidelines
1. **Import structure**: Each module adds project root to `sys.path` independently — allows running `python v1/app.py` from anywhere
2. **Config hierarchy**: `v2/config.py` imports and extends `common/config.py` — no duplication
3. **API keys**: Read once in `common/api_keys.py` — always check if key exists before calling APIs
4. **Test first**: Add test cases before implementing features

### Example: Adding a new ranking factor

**Option A** (affects both versions):
1. Add to `common/matcher.py` or create `common/new_factor.py`
2. Import in both `v1/engine.py` and `v2/engine.py`
3. Update `common/output.py` to display the new field
4. Add test case in `tests/validate_test_cases.py`

**Option B** (v2-specific):
1. Add to `v2/geopy_distance.py` or new `v2/new_module.py`
2. Import in `v2/engine.py`
3. Update `v2/config.py` if new config is needed
4. Add test case

## Adding a New Algorithm (e.g., v3)

```
v3/
├── __init__.py
├── app.py               (← copy from v2/app.py, change imports)
├── engine.py            (← main ranking logic)
├── config.py            (← extend common/config.py if needed)
└── algorithm.py         (← your new algorithm)
```

Update `main.py` to accept `v3` as a version argument.

## Commit Message Style

```
Describe what changed in one sentence

Optional: More context if needed. Reference what problem this solves
or what pattern it establishes for similar changes.

Examples:
  - Add fuzzy matching for special characters
  - Fix: v2 distance calculation exceeds 1000km boundary
  - Refactor: extract text_utils from matcher.py
```

## Before Submitting a PR

1. **Run tests**: `python -m tests.validate_test_cases`
2. **Check imports**: Verify module can run standalone (`python v1/app.py`)
3. **Update README**: If behavior or usage changes
4. **Add test cases**: For new features or bug fixes
5. **No keys in code**: Use environment variables for all secrets

## Common Tasks

### Add a new dependency
```bash
pip install <package>
# Update requirements.txt with version:
pip freeze | grep <package> >> requirements.txt
```

### Test a change across both versions
```bash
python main.py v1 --address "Test Address"
python main.py v2 --address "Test Address"
python -m tests.validate_test_cases
```

### Debug a specific lookup
```bash
# Add debug output to common/matcher.py or v1/engine.py
# Run interactive mode
python main.py
# Enter test case
```

## Reporting Issues

When submitting a bug report, include:
- Python version (`python --version`)
- Steps to reproduce
- Expected vs actual output
- Environment (v1 or v2, which API keys set)
