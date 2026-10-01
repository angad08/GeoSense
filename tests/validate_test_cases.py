"""Offline acceptance checks for GeoSense's address-first nearest-three rule.

The previous 22-check text-ladder harness is retained as
``tests/legacy_validate_test_cases.py`` for historical reference. It asserts
the former behavior and is not a current acceptance test.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

import v2.engine as engine
from v2.geopy_distance import MeasuredResults


class NearestThreeTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame([
            {"DISTRICT": "NORTH", "POLICE STATION": "APPLICANT GUESS",
             "STATE": "TELANGANA"},
            {"DISTRICT": "SOUTH", "POLICE STATION": "NEAREST",
             "STATE": "TELANGANA"},
            {"DISTRICT": "EAST", "POLICE STATION": "SECOND",
             "STATE": "TELANGANA"},
            {"DISTRICT": "WEST", "POLICE STATION": "THIRD",
             "STATE": "TELANGANA"},
            {"DISTRICT": "OTHER", "POLICE STATION": "AP STATION",
             "STATE": "ANDHRA PRADESH"},
        ])
        self.calls = []

    def fake_measure(self, address, stations, expected_state=None):
        self.calls.append((list(stations), expected_state))
        distances = {"APPLICANT GUESS": 12.0, "NEAREST": 1.0,
                     "SECOND": 2.0, "THIRD": 3.0, "AP STATION": 0.5}
        return MeasuredResults(
            [{"state": state, "district": district, "police_station": ps,
              "distance_km": distances[ps],
              "coordinate_unverified": ps == "SECOND"}
             for state, district, ps in stations],
            address_state="Telangana")

    def test_applicant_guess_and_district_do_not_filter_address(self):
        with patch.object(engine, "measure_from_address",
                          side_effect=self.fake_measure):
            result = engine.find_best_match(
                "12 Main Road, Telangana 500001", "APPLICANT GUESS",
                "NORTH", self.df, None)
        self.assertEqual([r["police_station"] for r in result["results"]],
                         ["NEAREST", "SECOND", "THIRD"])
        self.assertEqual([r["distance"] for r in result["results"]],
                         ["~1.0 km", "~2.0 km", "~3.0 km"])
        self.assertEqual(self.calls[0][1], "TELANGANA")
        self.assertEqual(len(self.calls[0][0]), 4)
        self.assertEqual(result["results"][1]["confidence"], "LOW")
        self.assertIn("shared", result["warning"])

    def test_without_state_uses_geocoded_state(self):
        with patch.object(engine, "measure_from_address",
                          side_effect=self.fake_measure):
            result = engine.find_best_match("12 Main Road 500001", "", "",
                                            self.df, None)
        self.assertEqual(result["results"][0]["police_station"], "NEAREST")
        self.assertEqual(len(self.calls[0][0]), 5)
        self.assertIsNone(self.calls[0][1])
        self.assertIn("TELANGANA", result["state_scope"])

    def test_failed_address_geocode_does_not_invent_ranking(self):
        with patch.object(engine, "measure_from_address", return_value=None):
            result = engine.find_best_match("Unknown, Telangana", "", "",
                                            self.df, None)
        self.assertEqual(result["case"], 0)
        self.assertEqual(result["results"], [])

    def test_unidentified_geocoded_state_does_not_rank_other_states(self):
        with patch.object(engine, "measure_from_address",
                          return_value=MeasuredResults([], address_state="")):
            result = engine.find_best_match("12 Main Road 500001", "", "",
                                            self.df, None)
        self.assertEqual(result["case"], 0)
        self.assertIn("state", result["method"].lower())

    def test_name_only_lookup_still_resolves_sheet_row(self):
        with patch.object(engine, "measure_from_address") as measure:
            result = engine.find_best_match("", "NEAREST", "", self.df, None)
        self.assertEqual(result["results"][0]["district"], "SOUTH")
        measure.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
