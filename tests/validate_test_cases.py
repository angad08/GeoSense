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
               (the mock is only reached by the Case-2 distance-fill, #9),
               measure_from_address → None ("not geocoded") unless a distance
               test [19]-[22] supplies fake distances

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


# Stand-in for geopy_distance.measure_from_address — NO network. By default it
# behaves like "address could not be geocoded" (returns None), so every older
# test sees the text-only answer it always did. The distance tests [19]-[22]
# set _measure_km to a function (district, ps) -> km to fake real distances.
_measure_km    = None
_measure_calls = []


def _v2_fake_measure(input_address, stations):
    _measure_calls.append(len(stations))
    if _measure_km is None:
        return None
    return [{"police_station": ps, "district": d, "distance_km": _measure_km(d, ps)}
            for d, ps in stations]


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
    v2_engine.measure_from_address = _v2_fake_measure

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

    # ── COMPOSITE KEY: duplicate station names ────────────────────────────────
    # Station names legitimately repeat across districts. The lookup key is
    # (DISTRICT, POLICE STATION); a duplicated name must never be resolved by
    # Excel row order. Each check asserts the exact records returned.
    print("=" * 100)
    print("CASE 1 / 3a — composite key (duplicate station names)")
    print("=" * 100)

    def _pairs(res):
        return [(r["police_station"], r["district"]) for r in res["results"]]

    dup_checks = []

    # [10] Unique name — unchanged behaviour, district is not consulted.
    r = v2_engine.find_best_match("", "GACHIBOWLI", "", df, client)
    exp = [("GACHIBOWLI", "CYBERABAD-RANGAREDDY")]
    ok  = _pairs(r) == exp and r["confidence"] == "VERY HIGH"
    dup_checks.append(ok)
    print(f"[10] {'PASS' if ok else 'FAIL':10} unique station -> {_pairs(r)}  exp={exp}")

    # [11] Duplicate + correct district — district selects one valid record.
    # NAWABPET exists in MAHABUBNAGAR and VIKARABAD; sheet order would give
    # MAHABUBNAGAR, so returning VIKARABAD proves district, not row order, decided.
    r = v2_engine.find_best_match("", "NAWABPET", "VIKARABAD", df, client)
    exp = [("NAWABPET", "VIKARABAD")]
    ok  = _pairs(r) == exp and "resolved by district" in r.get("note", "")
    dup_checks.append(ok)
    print(f"[11] {'PASS' if ok else 'FAIL':10} dup + correct district -> {_pairs(r)}  exp={exp}")

    # [12] Duplicate + non-matching district — show every valid record, pick none.
    # No address, so no state is named and every state is searched: the AP
    # record (SRI POTTI SRIRAMULU NELLORE) is a valid candidate too. Order is by
    # district name (matcher tie-break), not sheet row.
    r = v2_engine.find_best_match("", "NAWABPET", "HYDERABAD", df, client)
    exp = [("NAWABPET", "MAHABUBNAGAR"), ("NAWABPET", "SRI POTTI SRIRAMULU NELLORE"),
           ("NAWABPET", "VIKARABAD")]
    ok  = _pairs(r) == exp and "select the correct record" in r.get("note", "")
    dup_checks.append(ok)
    print(f"[12] {'PASS' if ok else 'FAIL':10} dup + non-matching district -> {_pairs(r)}  exp={exp}")

    # [13] 3a duplicate locality — the address names BALANAGAR but no district,
    # so both valid records must surface as distinct candidates rather than one
    # being silently dropped by drop_duplicates.
    dup_addr = "7-8-237 GOUTHAM NAGAR , FEROZGUDA,BALANAGAR,telangana, pin 500011"
    hits = find_ps_by_localities(dup_addr, df)
    got  = [(h["police_station"], h["district"]) for h in hits]
    exp  = [("BALANAGAR", "CYBERABAD-MEDCHAL"), ("BALANAGAR", "MAHABUBNAGAR")]
    ok   = got == exp
    dup_checks.append(ok)
    print(f"[13] {'PASS' if ok else 'FAIL':10} 3a duplicate locality -> {got}")
    print(f"     exp={exp}")

    # [14] 3a free disambiguation — same shape, but this address names the
    # district too, so exactly one record should survive without any API call.
    nb_addr = "1-10/1, NAWABPET,POMAL,MAHABUBNAGAR,TELANGANA PIN 509202"
    got14 = [(h["police_station"], h["district"])
             for h in find_ps_by_localities(nb_addr, df)]
    exp14 = [("NAWABPET", "MAHABUBNAGAR")]
    ok14  = got14 == exp14
    dup_checks.append(ok14)
    print(f"[14] {'PASS' if ok14 else 'FAIL':10} 3a disambiguated by address text -> {got14}  exp={exp14}")

    dup_ok = sum(dup_checks)

    # ── STATE FILTER ──────────────────────────────────────────────────────────
    # The address names its state; only that state's stations may be returned.
    # Both versions must agree (the filter is shared, ahead of the ladder).
    print("=" * 100)
    print("STATE FILTER — address names the state (V1 and V2)")
    print("=" * 100)

    state_checks = []

    ap_districts = set(df[df["STATE"] == "ANDHRA PRADESH"]["DISTRICT"])
    ts_districts = set(df[df["STATE"] == "TELANGANA"]["DISTRICT"])

    def _state_check(num, label, address, ps, exp, scope_has, v1_exact=True):
        r1 = v1_engine.find_best_match(address, ps, "", df, client)
        r2 = v2_engine.find_best_match(address, ps, "", df, client)
        # v1_exact=False: v1's Case 1 has always returned a single best hit
        # (no duplicate-record handling — that is v2 only, see [10]-[12]), so
        # there v1 is held only to the state rule: nothing from the other state.
        other = ap_districts if "TELANGANA" in scope_has else ts_districts
        v1_ok = (_pairs(r1) == exp if v1_exact
                 else bool(r1["results"]) and not any(d in other for _, d in _pairs(r1)))
        ok = (v1_ok and _pairs(r2) == exp
              and scope_has in r2.get("state_scope", ""))
        state_checks.append(ok)
        print(f"[{num}] {'PASS' if ok else 'FAIL':10} {label} -> V2 {_pairs(r2)}")
        if not ok:
            print(f"     exp={exp}  V1={_pairs(r1)}  scope={r2.get('state_scope')!r}")

    # [15] Telangana address, NAWABPET named, no district — the AP NAWABPET
    # must not appear.
    _state_check(15, "TS address, dup name",
                 "1-10/1, NAWABPET,POMAL,TELANGANA PIN 509202", "",
                 [("NAWABPET", "MAHABUBNAGAR"), ("NAWABPET", "VIKARABAD")],
                 "only TELANGANA")

    # [16] Andhra Pradesh address, same name — only the AP record.
    _state_check(16, "AP address, dup name",
                 "3-45, MAIN BAZAR, NAWABPET, ANDHRA PRADESH 524001", "",
                 [("NAWABPET", "SRI POTTI SRIRAMULU NELLORE")],
                 "only ANDHRA PRADESH")

    # [17] Case 1 (known PS typed) with a Telangana address — the state
    # applies here too, so the AP record is never offered. v1 returns one
    # best hit on this path (pre-existing), so it is checked for state only.
    _state_check(17, "known PS + TS address",
                 "1-10/1, POMAL, TELANGANA PIN 509202", "NAWABPET",
                 [("NAWABPET", "MAHABUBNAGAR"), ("NAWABPET", "VIKARABAD")],
                 "only TELANGANA", v1_exact=False)

    # [18] Misspelt state still narrows.
    _state_check(18, "misspelt state (TELENGANA)",
                 "1-10/1, NAWABPET,POMAL,TELENGANA PIN 509202", "",
                 [("NAWABPET", "MAHABUBNAGAR"), ("NAWABPET", "VIKARABAD")],
                 "only TELANGANA")

    state_ok = sum(state_checks)

    # ── DISTANCE RULES (V2 only — v1 has no geocoding) ────────────────────────
    # Rule 2: a station named in the address has priority, verified by distance.
    # Rule 1: no state named and nothing named by text → nearest, all states.
    # Distances are faked via _measure_km; no network.
    print("=" * 100)
    print("DISTANCE RULES — verify text hits / nearest when no state (V2 only)")
    print("=" * 100)

    global _measure_km
    state_of = dict(zip(zip(df["DISTRICT"], df["POLICE STATION"]), df["STATE"]))
    dist_checks = []

    # [19] Rule 2, no state named: ATMAKUR matches 6 records in two states. The
    # one near the address (WANAPARTHY, 4 km) must come first; the rest are
    # still listed (never dropped) but marked LOW because they are far.
    _measure_km = lambda d, ps: (4.0 if (d, ps) == ("WANAPARTHY", "ATMAKUR")
                                 else 150.0 if state_of[(d, ps)] == "TELANGANA" else 300.0)
    r   = v2_engine.find_best_match("H NO 4-2, MAIN ROAD, ATMAKUR, PIN 509131", "", "", df, client)
    exp = [("ATMAKUR", "WANAPARTHY"), ("ATHMAKUR", "WARANGAL-HANUMAKONDA"),
           ("ATHMAKUR", "YADADRI BHUVANAGIRI")]
    ok  = (_pairs(r) == exp and r["results"][0]["distance"] == "~4.0 km"
           and r["results"][0]["confidence"] == "HIGH"
           and [x["confidence"] for x in r["results"][1:]] == ["LOW", "LOW"]
           and "verified by geodesic distance" in r["method"] and "warning" not in r)
    dist_checks.append(ok)
    print(f"[19] {'PASS' if ok else 'FAIL':10} text hits ordered by distance -> "
          f"{[(x['police_station'], x['district'], x['distance']) for x in r['results']]}")

    # [20] Rule 2, named station is far from the address: still returned (text
    # has priority), but downgraded to LOW with a warning.
    _measure_km = lambda d, ps: 80.0
    r   = v2_engine.find_best_match("1-10/1, NAWABPET,POMAL,TELANGANA PIN 509202", "", "", df, client)
    ok  = (_pairs(r) == [("NAWABPET", "MAHABUBNAGAR"), ("NAWABPET", "VIKARABAD")]
           and r["confidence"] == "LOW" and "80.0 km" in r.get("warning", ""))
    dist_checks.append(ok)
    print(f"[20] {'PASS' if ok else 'FAIL':10} far text hit flagged -> conf={r['confidence']} "
          f"warning={r.get('warning', '')[:60]!r}")

    # [21] Rule 1: no state, no station or district named → nearest stations
    # across every state, by distance.
    near = {("CYBERABAD-MEDCHAL", "PETBASHEERABAD"): 2.5, ("CYBERABAD-MEDCHAL", "DUNDIGAL"): 6.0,
            ("CYBERABAD-MEDCHAL", "MEDCHAL"): 9.0}
    _measure_km = lambda d, ps: near.get((d, ps), 500.0)
    _measure_calls.clear()
    r   = v2_engine.find_best_match("H NO 5-2-88, VENKATESHWARA COLONY, KOMPALLY, PIN 500014",
                                    "", "", df, client)
    exp = [("PETBASHEERABAD", "CYBERABAD-MEDCHAL"), ("DUNDIGAL", "CYBERABAD-MEDCHAL"),
           ("MEDCHAL", "CYBERABAD-MEDCHAL")]
    ok  = (_pairs(r) == exp and "all states" in r["method"]
           and _measure_calls == [len(df)] and "not named" in r["state_scope"])
    dist_checks.append(ok)
    print(f"[21] {'PASS' if ok else 'FAIL':10} no state -> nearest of all {len(df)} stations -> "
          f"{[(x['police_station'], x['distance']) for x in r['results']]}")

    # [22] Rule 1 does NOT run when the state is named: same address plus
    # TELANGANA stays inside Telangana and never ranks all states.
    _measure_calls.clear()
    r   = v2_engine.find_best_match("H NO 5-2-88, VENKATESHWARA COLONY, KOMPALLY, TELANGANA PIN 500014",
                                    "", "", df, client)
    ok  = _measure_calls == [] and "all states" not in r["method"]
    dist_checks.append(ok)
    print(f"[22] {'PASS' if ok else 'FAIL':10} state named -> no all-states ranking "
          f"(measure calls={_measure_calls}, case={r['case']})")

    _measure_km = None
    dist_ok = sum(dist_checks)

    print("=" * 100)
    overall = (v1_pass == 6 and v2_pass == 6 and parity == len(CASES)
               and neg_ok == len(NEGATIVE_CASES) and pin_ok
               and dup_ok == len(dup_checks) and state_ok == len(state_checks)
               and dist_ok == len(dist_checks))
    print(f"SUMMARY  V1 rank-1 {v1_pass}/7 | V2 rank-1 {v2_pass}/7 | parity {parity}/7 | "
          f"negative {neg_ok}/{len(NEGATIVE_CASES)} | case-2 pin {int(pin_ok)}/1 | "
          f"duplicates {dup_ok}/{len(dup_checks)} | state {state_ok}/{len(state_checks)} | distance {dist_ok}/{len(dist_checks)}  "
          f"=> {'ALL GREEN' if overall else 'REGRESSION'}")
    print("=" * 100)
    return overall


if __name__ == "__main__":
    run()
