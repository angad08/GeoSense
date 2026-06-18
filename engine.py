"""
GeoSense — engine.py
---------------------
Main decision logic. Routes each query to the correct case and returns a
structured result dict.

  Case 1 — Known PS       → fuzzy match Excel → STOP (no AI)
  Case 2 — Known District → filter Excel → AI ranks by address
  Case 3 — Address only   → AI infers district → AI ranks PS
  Case 0 — Nothing worked → empty result
"""

from config import COL_DISTRICT, COL_PS, TOP_N, AI_PROVIDER, AI_MODEL, FUZZY_CUTOFF
from matcher import (
    find_ps_in_excel,
    find_district_in_excel,
    find_ps_by_localities,
    find_district_by_localities,
)
from ai_engine import rankingAgent, inferDistrict


def find_best_match(address, known_ps, known_district, df, client):
    """
    Routes to the correct case based on what the user has provided.

    Parameters
    ----------
    address        : full address string (may be empty)
    known_ps       : police station name as entered (may be empty)
    known_district : district name as entered (may be empty)
    df             : standardised Excel DataFrame from loader.load_excel()
    client         : AI client from ai_engine.initiateAgent()

    Returns
    -------
    dict with keys: case, confidence, method, results
    Each item in results: rank, police_station, district, confidence,
                          match_score (Case 1 only), distance
    """

    # ── CASE 1: Known Police Station ─────────────────────────────────────────
    if known_ps.strip():
        hits = find_ps_in_excel(known_ps, df)

        if hits:
            best       = hits[0]
            confidence = "VERY HIGH" if best["score"] == 100 else "HIGH"
            return {
                "case":       1,
                "confidence": confidence,
                "method":     f"{'Exact' if best['score'] == 100 else 'Fuzzy'} match "
                              f"on Police Station (score: {best['score']}%)",
                "results": [{
                    "rank":           1,
                    "police_station": best["police_station"],
                    "district":       best["district"],
                    "confidence":     confidence,
                    "match_score":    best["score"],
                    "distance":       "N/A",
                }],
            }

        # PS given but not found — warn, fall through
        print(f"\n  [WARN] '{known_ps}' not found in Excel (threshold: {FUZZY_CUTOFF}%).")
        print(f"         Trying district/address...\n")

    # ── CASE 2: Known District ────────────────────────────────────────────────
    if known_district.strip():
        hits = find_district_in_excel(known_district, df)

        if hits:
            matched_dist   = hits[0]["district"]
            ps_in_district = df[df[COL_DISTRICT] == matched_dist]

            ps_list = ps_in_district[COL_PS].tolist()

            if address.strip():
                ranked = rankingAgent(address, matched_dist, ps_list, client)
            else:
                ranked = [{"police_station": ps, "distance": "N/A"} for ps in ps_list[:TOP_N]]

            results = [{
                "rank":           i + 1,
                "police_station": item["police_station"],
                "district":       matched_dist,
                "confidence":     "HIGH" if i == 0 else "MEDIUM",
                "distance":       item.get("distance", "N/A"),
            } for i, item in enumerate(ranked)]

            return {
                "case":       2,
                "confidence": "HIGH",
                "method":     f"District matched: {matched_dist} ({hits[0]['score']}%) | "
                              + ("AI ranked by address" if address.strip() else "no address, first N returned"),
                "results":    results,
            }

        print(f"\n  [WARN] District '{known_district}' not found in Excel.")
        print(f"         Falling back to address-only reasoning...\n")

    # ── CASE 3: Address only ──────────────────────────────────────────────────
    if address.strip():

        # 3a — Deterministic locality scan: does the address itself name a
        #      Police Station? (e.g. 'OLD BOWENPALLY' → 'BOWENPALLY PS')
        #      Excel is the source of truth, so this is tried before any AI.
        ps_hits = find_ps_by_localities(address, df)
        if ps_hits:
            results = [{
                "rank":           i + 1,
                "police_station": h["police_station"],
                "district":       h["district"],
                "confidence":     "HIGH" if h["score"] >= 95 else "MEDIUM",
                "match_score":    h["score"],
                "distance":       "N/A",
            } for i, h in enumerate(ps_hits[:TOP_N])]

            top = ps_hits[0]
            return {
                "case":       3,
                "confidence": "HIGH" if top["score"] >= 95 else "MEDIUM",
                "method":     f"Locality '{top['locality']}' from address matched "
                              f"Police Station in Excel (score: {top['score']}%)",
                "results":    results,
            }

        # 3b — Locality scan against District column: address names a district /
        #      zone (e.g. 'SECUNDERABAD'). Narrow to it, then AI-rank by address.
        dist_hits = find_district_by_localities(address, df)
        if dist_hits:
            matched_dist = dist_hits[0]["district"]
            ps_list      = df[df[COL_DISTRICT] == matched_dist][COL_PS].tolist()
            ranked       = rankingAgent(address, matched_dist, ps_list, client)

            results = [{
                "rank":           i + 1,
                "police_station": item["police_station"],
                "district":       matched_dist,
                "confidence":     "HIGH" if i == 0 else "MEDIUM",
                "distance":       item.get("distance", "N/A"),
            } for i, item in enumerate(ranked)]

            return {
                "case":       3,
                "confidence": "MEDIUM",
                "method":     f"Locality '{dist_hits[0]['locality']}' from address matched "
                              f"District: {matched_dist} ({dist_hits[0]['score']}%) | AI ranked PS",
                "results":    results,
            }

        # 3c — Pure AI geographic reasoning (last resort)
        ai_results = inferDistrict(address, df, client)

        if ai_results:
            for i, r in enumerate(ai_results):
                r["rank"] = i + 1
            return {
                "case":       3,
                "confidence": "MEDIUM",
                "method":     f"AI geographic reasoning | provider: {AI_PROVIDER} | model: {AI_MODEL}",
                "results":    ai_results,
            }

    # ── CASE 0: Nothing worked ────────────────────────────────────────────────
    return {
        "case":       0,
        "confidence": "NONE",
        "method":     "Could not determine a match",
        "results":    [],
    }
