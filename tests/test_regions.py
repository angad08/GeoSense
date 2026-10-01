"""Offline tests for multi-state behaviour: Tamil Nadu / Andhra Pradesh name
formats, state scoping, coordinate checks, and relisted stations. No network."""

import unittest
from unittest.mock import patch

import pandas as pd

from common.matcher import (
    locality_score, score_match, find_ps_by_localities, _normalize,
)
from common.state_filter import filter_by_state
from v2 import engine
from v2 import geopy_distance as geo


def _sheet():
    rows = [
        ("TELANGANA",      "HYDERABAD",                "BORABANDA"),
        ("TELANGANA",      "JAYASHANKAR BHUPALPALLY",  "GHANPUR (MULUGU)"),
        ("TELANGANA",      "KOMARAMBHEEM ASIFABAD",    "SIRPUR(U)"),
        ("ANDHRA PRADESH", "YSR DISTRICT",             "MYDUKUR U/G"),
        ("ANDHRA PRADESH", "YSR DISTRICT",             "PRODDATUR II TOWN"),
        ("TAMIL NADU",     "CHENNAI",                  "K-4 ANNANAGAR"),
        ("TAMIL NADU",     "CHENNAI",                  "H-6 R.K. NAGAR"),
        ("TAMIL NADU",     "THENI",                    "ALL WOMEN PS BODI"),
        ("TAMIL NADU",     "THENI",                    "BODI TOWN"),
        ("TAMIL NADU",     "ERODE",                    "AMMAPETTAI P.S"),
    ]
    return pd.DataFrame(rows, columns=["STATE", "DISTRICT", "POLICE STATION"])


class NameFormatTests(unittest.TestCase):
    def test_variants_match_the_plain_place_name(self):
        for token, station in [("MYDUKUR", "MYDUKUR U/G"),
                               ("GHANPUR", "GHANPUR (MULUGU)"),
                               ("SIRPUR", "SIRPUR(U)"),
                               ("AMMAPETTAI", "AMMAPETTAI P.S"),
                               ("TP CHATRAM", "K-6 T.P.CHATRAM"),
                               ("RK NAGAR", "H-6 R.K. NAGAR")]:
            self.assertEqual(locality_score(token, station), 100, (token, station))

    def test_all_women_station_formats_are_equal(self):
        self.assertEqual(_normalize("ALL WOMEN PS BODI"), "BODI AWPS")
        self.assertEqual(_normalize("ALL WOMEN POLICE STATION THENI"), "THENI AWPS")
        self.assertEqual(_normalize("ALL WOMEN UTHAMAPLAYAM"), "UTHAMAPLAYAM AWPS")
        self.assertEqual(score_match("BODI AWPS", "ALL WOMEN PS BODI"), 100)

    def test_fragments_and_qualifiers_never_match_alone(self):
        # Invariant I2: no new route for a generic or bracketed word.
        for token, station in [("NAGAR", "K-4 ANNANAGAR"),
                               ("MULUGU", "GHANPUR (MULUGU)"),
                               ("BEGAMPET", "RAIPOL (BEGAMPET)"),
                               ("BODI", "ALL WOMEN PS BODI"),
                               ("TOWN", "PRODDATUR II TOWN")]:
            self.assertLess(locality_score(token, station), 86, (token, station))


class AddressTests(unittest.TestCase):
    def test_tamil_nadu_address_finds_coded_chennai_station(self):
        hits = find_ps_by_localities(
            "12, 3RD STREET, ANNA NAGAR, CHENNAI, TAMIL NADU 600040", _sheet())
        self.assertEqual(hits[0]["police_station"], "K-4 ANNANAGAR")

    def test_andhra_address_finds_upgraded_station(self):
        hits = find_ps_by_localities(
            "D NO 4-12, MAIN ROAD, MYDUKUR, KADAPA, ANDHRA PRADESH 516172", _sheet())
        self.assertEqual(hits[0]["police_station"], "MYDUKUR U/G")

    def test_bracket_kept_when_it_separates_same_name_stations(self):
        # SIRPUR(U) and SIRPUR TOWN: the town of Sirpur Kaghaznagar must not be
        # answered by SIRPUR(U) just because its bracket was dropped.
        sheet = pd.concat([_sheet(), pd.DataFrame(
            [("TELANGANA", "KOMARAMBHEEM ASIFABAD", "SIRPUR TOWN")],
            columns=["STATE", "DISTRICT", "POLICE STATION"])])
        hits = find_ps_by_localities("H NO 2-11, SIRPUR, KOMARAM BHEEM, TELANGANA", sheet)
        self.assertNotIn("SIRPUR(U)", [h["police_station"] for h in hits])
        hits = find_ps_by_localities("H NO 2-11, SIRPUR, KOMARAM BHEEM, TELANGANA", _sheet())
        self.assertEqual(hits[0]["police_station"], "SIRPUR(U)")   # unique: allowed

    def test_generic_address_words_match_nothing(self):
        self.assertEqual(find_ps_by_localities(
            "FLAT 2, NEW NAGAR, MAIN ROAD, TAMIL NADU", _sheet()), [])

    def test_state_named_in_address_limits_the_search(self):
        scoped, _, state = filter_by_state("ANNA NAGAR, CHENNAI, TAMIL NADU", _sheet())
        self.assertEqual(state, "TAMIL NADU")
        self.assertEqual(set(scoped["STATE"]), {"TAMIL NADU"})
        scoped, _, state = filter_by_state("BORABANDA, HYDERABAD", _sheet())
        self.assertIsNone(state)
        self.assertEqual(len(scoped), len(_sheet()))


class CoordinateCheckTests(unittest.TestCase):
    def test_clean_station_name(self):
        self.assertEqual(geo.clean_station_name("K-4 ANNANAGAR"), "ANNANAGAR")
        self.assertEqual(geo.clean_station_name("BHAVANI P.S"), "BHAVANI")
        self.assertEqual(geo.clean_station_name("P.N.PALAYAM"), "P.N.PALAYAM")

    def test_same_state_and_district_are_lenient_but_not_loose(self):
        self.assertTrue(geo.same_state("TAMIL NADU", "Tamil Nadu"))
        self.assertTrue(geo.same_state("JAMMU & KASHMIR", "Jammu and Kashmir"))
        self.assertFalse(geo.same_state("TELANGANA", "Andhra Pradesh"))
        self.assertTrue(geo.same_district("KOMARAMBHEEM ASIFABAD", "Kumuram Bheem Asifabad"))
        self.assertTrue(geo.same_district("TIRUCHIRAPPALLI RURAL", "Tiruchirappalli"))
        self.assertFalse(geo.same_district("KURNOOL", "Tirupati"))

    def test_area_centre_result_is_vague(self):
        self.assertTrue(geo.vague_result_type({"types": ["administrative_area_level_2"]}))
        self.assertFalse(geo.vague_result_type({"types": ["police", "establishment"]}))

    def test_station_far_from_its_district_is_isolated(self):
        coords = {("KURNOOL", f"S{i}"): (15.8 + i * 0.01, 78.0) for i in range(4)}
        self.assertEqual(geo.isolated_from_siblings(("KURNOOL", "S0"), 15.8, 78.0, coords), 0)
        far = geo.isolated_from_siblings(("KURNOOL", "GUDUR"), 13.9, 79.9, coords)
        self.assertGreater(far, 200)


class RestackTests(unittest.TestCase):
    """Moving a stacked station to its own village (Geocoding is mocked)."""

    COORDS = {("MADURAI RURAL", f"S{i}"): (9.9 + i * 0.05, 78.1) for i in range(4)}

    def _top(self, name, lat, lng, types=("locality", "political"), state="Tamil Nadu"):
        return {"types": list(types), "formatted_address": f"{name}, {state}",
                "geometry": {"location": {"lat": lat, "lng": lng}},
                "address_components": [
                    {"long_name": name, "types": list(types)},
                    {"long_name": state, "types": ["administrative_area_level_1"]}]}

    def _run(self, ps, top, old=(9.925, 78.12)):
        coords = dict(self.COORDS)
        coords[("MADURAI RURAL", ps)] = old
        with patch.object(geo, "_geocode_top", return_value=top), \
             patch.dict(geo._state_cache, {("MADURAI RURAL", ps): "TAMIL NADU"}):
            return geo.geocode_station_place("MADURAI RURAL", ps, coords)

    def test_place_name_drops_station_qualifiers(self):
        self.assertEqual(geo.station_place_name("ADILABAD II TOWN"), "ADILABAD")
        self.assertEqual(geo.station_place_name("NANDYAL TALUKA"), "NANDYAL")
        self.assertEqual(geo.station_place_name("K-4 ANNANAGAR"), "ANNANAGAR")
        self.assertEqual(geo.station_place_name("TENKASI AWPS"), "TENKASI")

    def test_moves_to_its_own_village(self):
        new, detail = self._run("MELUR", self._top("Melur", 10.03, 78.34))
        self.assertEqual(new, (10.03, 78.34))
        self.assertIn("Melur", detail)

    def test_keeps_point_when_place_name_differs(self):
        new, _ = self._run("RAJAHMUNDRY III TOWN", self._top("Rajamahendravaram", 10.0, 78.2))
        self.assertIsNone(new)

    def test_keeps_point_for_a_shop_or_other_non_place(self):
        new, _ = self._run("MELUR", self._top("Melur", 10.03, 78.34,
                                              types=("clothing_store", "establishment")))
        self.assertIsNone(new)

    def test_keeps_point_for_wrong_state_or_far_village(self):
        self.assertIsNone(self._run("MELUR", self._top("Melur", 10.03, 78.34,
                                                       state="Kerala"))[0])
        self.assertIsNone(self._run("MELUR", self._top("Melur", 12.9, 79.1))[0])


class RelistedStationTests(unittest.TestCase):
    def _result(self):
        return {"case": 3, "results": [
            {"rank": 1, "police_station": "NEMILI", "district": "VELLORE", "distance": "~1 km"},
            {"rank": 2, "police_station": "NEMILI", "district": "RANIPET", "distance": "~1 km"},
            {"rank": 3, "police_station": "BANAVARAM", "district": "RANIPET", "distance": "~6 km"},
        ]}

    def test_same_station_in_two_districts_shown_once(self):
        coords = {("VELLORE", "NEMILI"): (13.0, 79.6), ("RANIPET", "NEMILI"): (13.0, 79.6),
                  ("RANIPET", "BANAVARAM"): (13.05, 79.6)}
        result = self._result()
        with patch.object(engine, "_load_coords_cache", return_value=coords):
            engine._merge_relisted_stations(result)
        self.assertEqual([(r["rank"], r["police_station"], r["district"]) for r in result["results"]],
                         [(1, "NEMILI", "VELLORE / RANIPET"), (2, "BANAVARAM", "RANIPET")])
        self.assertIn("same station", result["note"])

    def test_same_name_far_apart_stays_separate(self):
        coords = {("VELLORE", "NEMILI"): (13.0, 79.6), ("RANIPET", "NEMILI"): (12.0, 79.6),
                  ("RANIPET", "BANAVARAM"): (13.05, 79.6)}
        result = self._result()
        with patch.object(engine, "_load_coords_cache", return_value=coords):
            engine._merge_relisted_stations(result)
        self.assertEqual(len(result["results"]), 3)
        self.assertNotIn("note", result)

    def test_missing_coordinate_never_merges(self):
        coords = {("VELLORE", "NEMILI"): (13.0, 79.6), ("RANIPET", "NEMILI"): None}
        result = self._result()
        with patch.object(engine, "_load_coords_cache", return_value=coords):
            engine._merge_relisted_stations(result)
        self.assertEqual(len(result["results"]), 3)


if __name__ == "__main__":
    unittest.main()
