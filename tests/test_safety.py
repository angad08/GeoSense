"""Offline regressions for failures found in the independent review."""

import unittest
from unittest.mock import patch

from common.matcher import locality_score
from common import lookup_log
from v2 import geopy_distance as geo


class SafetyTests(unittest.TestCase):
    def test_city_code_and_joined_name(self):
        self.assertEqual(locality_score("ANNA NAGAR", "K-4 ANNANAGAR"), 100)
        self.assertLess(locality_score("NAGAR", "K-4 ANNANAGAR"), 86)

    def test_stack_detector_keeps_distinct_rows(self):
        point = (10.0, 78.0)
        coords = {
            ("DISTRICT A", "TOWN PS"): point,
            ("DISTRICT A", "RURAL PS"): point,
            ("DISTRICT B", "UNRELATED"): (11.0, 79.0),
        }
        self.assertEqual(geo.coordinate_collisions(coords),
                         {("DISTRICT A", "TOWN PS"),
                          ("DISTRICT A", "RURAL PS")})

    def test_address_geocode_rejects_area_centre_and_conflicting_pin(self):
        broad = {
            "types": ["administrative_area_level_2"],
            "geometry": {"location": {"lat": 13.0, "lng": 80.0}},
            "formatted_address": "District, India",
        }
        with patch.object(geo, "_geocode_top", return_value=broad):
            self.assertIsNone(geo.geocode_address("Some village, 600001"))

        wrong_pin = {
            "types": ["street_address"],
            "geometry": {"location": {"lat": 13.0, "lng": 80.0}},
            "formatted_address": "Other street, 600002, India",
            "address_components": [
                {"long_name": "600002", "types": ["postal_code"]}
            ],
        }
        with patch.object(geo, "_geocode_top", return_value=wrong_pin):
            self.assertIsNone(geo.geocode_address("Some street, 600001"))

        wrong_state = dict(wrong_pin)
        wrong_state["address_components"] = [
            {"long_name": "Andhra Pradesh", "types": ["administrative_area_level_1"]}
        ]
        with patch.object(geo, "_geocode_top", return_value=wrong_state):
            self.assertIsNone(geo.geocode_address("Some street, Telangana",
                                                  expected_state="TELANGANA"))

    def test_distance_lookup_does_not_retry_blank_station(self):
        cache = {("DISTRICT", "MISSING"): None}
        with patch.object(geo, "_load_coords_cache", return_value=cache), \
             patch.object(geo, "geocode_address", return_value=((13.0, 80.0), "address")), \
             patch.object(geo, "geocode_station") as paid:
            result = geo.rank_ps_by_distance("address", ["MISSING"], "DISTRICT")
        self.assertEqual(result, [])
        self.assertEqual(result.excluded, ["MISSING"])
        paid.assert_not_called()

    def test_distance_lookup_uses_stateful_station_coordinates(self):
        station = ("SHARED DISTRICT", "CENTRAL")
        cache = {station: (13.0, 80.0)}
        stateful = {
            ("TELANGANA", *station): (17.0, 78.0),
            ("ANDHRA PRADESH", *station): (13.0, 80.0),
        }
        with patch.object(geo, "_load_coords_cache", return_value=cache), \
             patch.object(geo, "_stateful_coords_cache", stateful), \
             patch.object(geo, "geocode_address",
                          return_value=((17.0, 78.0), "address", "Telangana")):
            result = geo.measure_from_address(
                "address", [("TELANGANA", *station),
                            ("ANDHRA PRADESH", *station)])
        self.assertEqual(result[0]["distance_km"], 0)
        self.assertGreater(result[1]["distance_km"], 0)
        self.assertEqual(result.address_state, "Telangana")

    def test_bulk_write_pauses_new_different_name_collision(self):
        existing = {("DISTRICT", "TOWN"): (13.0, 80.0)}
        with patch.object(geo, "_load_coords_cache", return_value=existing), \
             patch.object(geo.openpyxl, "load_workbook") as load_workbook:
            geo._write_coords([("DISTRICT", "RURAL", 13.0, 80.0)])
        load_workbook.assert_not_called()

    def test_unrouted_lookup_is_included_in_measurement_log(self):
        with patch.object(lookup_log, "_append_row") as append:
            lookup_log.log_lookup({"case": 0, "results": []},
                                  "unmatched address", "", "", interactive=False)
        values = append.call_args.args[1]
        self.assertEqual(values["RESULT LOOKUP"], "NO RESULT")
        self.assertEqual(values["RESULT MATCH"], "No suggestion")
        self.assertEqual(values["PREDICTED PS"], "")


if __name__ == "__main__":
    unittest.main()
