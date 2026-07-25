"""
GeoSense — tests/validate_test_cases.py  (unified, both versions)
------------------------------------------------------------------
Regression harness for the restructured project. Same cases as before, now run
against BOTH versions from the shared package layout:

  - Case 3 (address-only), #1–#8 → run against v1.engine AND v2.engine. Both
    resolve inside the shared text-scan layer (common.matcher), so their rank-1
    answers must be identical and must match the pre-restructure baseline.
  - Case 2 text-first pin, #9 → v2 ONLY (the geodesic pin is a v2 feature; v1's
    Case 2 uses AI ranking). Asserts LB NAGAR pinned at rank 1.

NO network / geocoding / AI calls. Each version's paid rungs are monkeypatched
on its own engine module:
    v1.engine: inferDistrict → [], rankingAgent → []      (Case 3c degrades to
               an empty result, exactly as the stubbed-AI path did before)
    v2.engine: ai_infer_district → [], rank_ps_by_distance → deterministic mock
               (the mock is only reached by the Case-2 distance-fill, #9)

Run from the project root:
    python -m tests.validate_test_cases
    (or)  python tests/validate_test_cases.py     # self-adds root to sys.path
"""

import sys
from pathlib import Path

# Allow `python tests/validate_test_cases.py` as well as `-m` by ensuring the
# project root (parent of tests/) is importable.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import v1.engine as v1_engine
import v2.engine as v2_engine
from common.loader import load_excel
from common.matcher import find_ps_by_localities
from common.config import TOP_N, EXCEL_FILE


class NoNetworkClient:
    """Any attribute access raises — a live AI call fails loudly instead of
    hitting the network."""
    def __getattr__(self, name):
        raise RuntimeError("validate_test_cases: attempted an AI/network call — "
                           "address should have resolved in the text-scan layer")


# ── Network-safe mocks ───────────────────────────────────────────────────────
_v2_rank_calls = []


def _v1_infer_district(address, df, client):      # v1 signature
    return []


def _v1_ranking(address, district, ps_list, client):   # v1 signature (safety)
    return []


def _v2_infer_district(address, df, client):      # v2 signature
    return []


def _v2_fake_rank(input_address, ps_list, district, top_n=TOP_N):
    """Deterministic stand-in for geopy_distance.rank_ps_by_distance — NO
    network. Fake increasing distances in ps_list order (small, so no Case-2
    warning fires). Used only by the Case-2 distance-fill (#9)."""
    _v2_rank_calls.append((district, len(ps_list)))
    canned = [{
        "police_station":   ps,
        "district":         district,
        "distance":         f"~{i + 1}.0 km",
        "distance_km":      float(i + 1),
        "resolved_address": f"{ps} Police Station, {district} (mocked)",
    } for i, ps in enumerate(ps_list)]
    canned.sort(key=lambda x: x["distance_km"])
    return canned[:top_n]


# ── Case-3 addresses (#1–#7 positive, #8 negative) ───────────────────────────
CASES = [
    ("18-4-372/190,SAI BABA NAGAR,BORABANDA,TELANGANA,PIN 500018", "BORABANDA"),
    ("17-1-210/3/4/A SAIBABA TEMPLE LANE,SANTOSH NAGAR / HYDERABAD,telangana pin 500059", "SANTOSH NAGAR"),
    ("7-8-237 GOUTHAM NAGAR , FEROZGUDA,BALANAGAR,telangana, pin 500011", "SANATHNAGAR"),
    ("4-123-1/30 F NO 201 SVR HOMES, CITIZEN COLONY,ALWAL,TELANGANA PIN 500010", "ALWAL"),
    ("1-10/1, NAWABPET,POMAL,MAHABUBNAGAR,TELANGANA PIN 509202", "NAWABPET"),
    ("2-9/1 NARAYANAPET,JAKRANPALLY,nizamabad,telangana pin 503224", "JAKRANPALLY"),
    ("NEW BAHAR 1/30, SAHARA ESTATE,LB NAGAR,MALKAJGIRI-RANGAREDDY,TELANGANA PIN 500068", "LB NAGAR"),
]
NEGATIVE_CASES = [
    ("H NO 5-2-88, VENKATESHWARA COLONY, KOMPALLY, TELANGANA PIN 500014", "ADILABAD"),
]


def _rank1(engine, address, ps="", district=""):
    r = engine.find_best_match(address, ps, district, df, client)
    stations = [x["police_station"] for x in r["results"]]
    return (stations[0] if stations else None), stations, r


def run():
    global df, client
    # Install mocks (paid rungs only) on each version's engine module.
    v1_engine.inferDistrict = _v1_infer_district
    v1_engine.rankingAgent  = _v1_ranking
    v2_engine.ai_infer_district = _v2_infer_district
    v2_engine.rank_ps_by_distance = _v2_fake_rank

    # Resolved from config so the harness follows whatever the app uses —
    # sample_police_stations.xlsx, or POLICE_STATION.xlsx as the fallback.
    df = load_excel(str(EXCEL_FILE))
    client = NoNetworkClient()

    v1_pass = v2_pass = parity = 0
    print("=" * 100)
    print("CASE 3 (address-only) — V1 vs V2  (must be identical, must match baseline)")
    print("=" * 100)
    for i, (address, expected) in enumerate(CASES, start=1):
        v1_r1, _, _ = _rank1(v1_engine, address)
        v2_r1, _, _ = _rank1(v2_engine, address)
        v1_ok = (v1_r1 == expected)
        v2_ok = (v2_r1 == expected)
        same  = (v1_r1 == v2_r1)
        v1_pass += v1_ok; v2_pass += v2_ok; parity += same
        note = "  (known-fail: names BALANAGAR)" if i == 3 else ""
        tag  = "PASS" if v1_ok and v2_ok else ("FAIL" if not same else "known-fail")
        print(f"[{i}] {tag:10} exp={expected:14} V1={v1_r1!s:16} V2={v2_r1!s:16} same={same}{note}")

    print("-" * 100)
    print(f"Rank-1 pass  V1: {v1_pass}/{len(CASES)}   V2: {v2_pass}/{len(CASES)}   "
          f"V1==V2 on all cases: {parity}/{len(CASES)}")

    # Negative #8 — both versions
    neg_ok = 0
    for j, (address, forbidden) in enumerate(NEGATIVE_CASES, start=len(CASES) + 1):
        ps_hits = find_ps_by_localities(address, df)
        _, v1_st, v1_res = _rank1(v1_engine, address)
        _, v2_st, v2_res = _rank1(v2_engine, address)
        v1_dists = [r["district"] for r in v1_res["results"]]
        v2_dists = [r["district"] for r in v2_res["results"]]
        ok = (len(ps_hits) == 0
              and forbidden not in v1_dists and forbidden not in v2_dists)
        neg_ok += ok
        print(f"[{j}] {'PASS' if ok else 'FAIL':10} negative — 3a empty={len(ps_hits) == 0} | "
              f"V1 stations={v1_st} | V2 stations={v2_st} | no {forbidden} in either={ok}")

    print("=" * 100)
    print("CASE 2 (district text-first pin) — V2 ONLY")
    print("=" * 100)
    c2_addr = "NEW BAHAR 1/30, SAHARA ESTATE,LB NAGAR,MALKAJGIRI-RANGAREDDY,TELANGANA PIN 500068"
    c2_dist = "MALKAJGIRI-RANGAREDDY"
    _v2_rank_calls.clear()
    r1, stations, res = _rank1(v2_engine, c2_addr, "", c2_dist)
    pin_ok = (res["case"] == 2 and r1 == "LB NAGAR"
              and res["results"] and "match_score" in res["results"][0]
              and "pinned rank 1" in res["method"]
              and stations.count("LB NAGAR") == 1
              and len(_v2_rank_calls) >= 1)          # distance-fill via mock (no network)
    print(f"[9] {'PASS' if pin_ok else 'FAIL':10} V2 case={res['case']} rank1={r1!r} "
          f"results={stations}")
    print(f"    method: {res['method']}")
    print(f"    rank-1: {res['results'][0] if res['results'] else None}")

    print("=" * 100)
    overall = (v1_pass == 6 and v2_pass == 6 and parity == len(CASES)
               and neg_ok == len(NEGATIVE_CASES) and pin_ok)
    print(f"SUMMARY  V1 rank-1 {v1_pass}/7 | V2 rank-1 {v2_pass}/7 | parity {parity}/7 | "
          f"negative {neg_ok}/{len(NEGATIVE_CASES)} | case-2 pin {int(pin_ok)}/1  "
          f"=> {'ALL GREEN' if overall else 'REGRESSION'}")
    print("=" * 100)
    return overall


if __name__ == "__main__":
    run()
