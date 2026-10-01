# Contributing to GeoSense

Read [README.md](README.md) and [ARCHITECTURE.md](ARCHITECTURE.md) before changing the ranking. The current v2 contract is: **for an address, display the three nearest located station rows in the detected state, with distances**. Applicant-supplied station and district names are hints. No station row may be deleted, merged, renamed, or deduplicated in `data/POLICE_STATION.xlsx`.

Run the offline acceptance checks after a code change:

```bash
python tests/validate_test_cases.py
python -m unittest tests.test_safety
python scripts/build_ps_coords.py --dry-run
```

The first two commands mock Google and must make no API calls. The dry run prints proposed station queries without writing the workbook. `tests/legacy_validate_test_cases.py` is the previous ladder test and is retained as a historical reference, not a current acceptance gate.

For coordinate work, keep Excel closed. `scripts/build_ps_coords.py` is the explicit paid maintenance command; ordinary lookups never fill blank station coordinates. A new different-name exact-coordinate collision must remain unresolved for review. Do not hardcode state lists or regional boxes: derive states from the workbook or Google's response.

Document any changed ranking behavior and add a test that checks its observable effect on the top three or its failure handling. Compare costs in API calls before using live Google or AI services. Never commit keys or applicant addresses.
