"""
GeoSense — engine.py
---------------------
Main decision logic. Routes each query to the correct case.

The ladder — each rung only runs if the one before it could not answer,
so cost is only incurred when it has to be:

    fuzzy match  →  locality scan  →  geocoding  →  AI
    (free)          (free)            (paid)        (paid, last resort)

  Case 1  — Known PS       → fuzzy match Excel → done (no geocoding, no AI)
  Case 2  — Known District → filter Excel → geocode → rank by real distance
  Case 3a — Address names a PS       → Excel only, no geocoding, no AI
  Case 3b — Address names a district → geocode → rank by real distance, no AI
  Case 3c — Address unmatched        → AI infers district → geocode → rank
  Case 0  — Nothing worked → empty result

AI is only ever called in Case 3c, and only to infer a district from text.
All distance ranking uses real coordinates from the Geocoding API.
"""

from v2.config import (
    COL_DISTRICT, COL_PS, TOP_N, FUZZY_CUTOFF,
    DISTANCE_WARN_KM, AI_PROVIDER, AI_MODEL,
)
from common.matcher import (
    find_ps_in_excel,
    resolve_ps_with_district,
    find_district_in_excel,
    find_ps_by_localities,
    find_district_by_localities,
)
from v2.ai_engine import ai_infer_district
from v2.geopy_distance import rank_ps_by_distance


def find_best_match(address, known_ps, known_district, df, ai_client):
    """
    Route to the correct case based on what the user has provided.

    Parameters
    ----------
    address        : full address string (may be empty)
    known_ps       : police station name as entered (may be empty)
    known_district : district name as entered (may be empty)
    df             : standardised Excel DataFrame from loader.load_excel()
    ai_client      : AI client from ai_engine.init_ai_client()

    Returns
    -------
    dict with keys: case, confidence, method, results
                    + warning (optional — Case 2 only, see below)
    Each result item: rank, police_station, district, confidence, distance
                      + match_score (Case 1 only)
                      + resolved_address (Cases 2 and 3)

    `warning` is advisory text only. It is attached when the nearest PS in a
    user-stated district is farther than DISTANCE_WARN_KM from the geocoded
    address. It never alters routing, ranking or which results are returned.
    """

    # ── CASE 1: Known Police Station ──────────────────────────────────────────
    # Pure fuzzy match — no geocoding, no AI. Fast and free.
    if known_ps.strip():
        hits, status = resolve_ps_with_district(known_ps, df, known_district)

        if hits:
            best       = hits[0]
            confidence = "VERY HIGH" if best["score"] == 100 else "HIGH"
            kind       = "Exact" if best["score"] == 100 else "Fuzzy"

            # A station name that exists in several districts is several valid
            # records, not one. Unless the district picked exactly one of them,
            # every candidate is returned and the user selects — choosing
            # between known rows is a selection, never an inference, so no
            # geocoding or AI call is made here.
            out = {
                "case":       1,
                "confidence": confidence if status != "ambiguous" else "MEDIUM",
                "method":     f"{kind} match on Police Station (score: {best['score']}%)"
                              + (f" | duplicate station name — resolved by district "
                                 f"{best['district']}" if status == "resolved_by_district"
                                 else ""),
                "results": [{
                    "rank":           i + 1,
                    "police_station": h["police_station"],
                    "district":       h["district"],
                    "confidence":     confidence if status != "ambiguous" else "MEDIUM",
                    "match_score":    h["score"],
                    "distance":       "N/A",
                } for i, h in enumerate(hits)],
            }

            if status == "resolved_by_district":
                out["note"] = ("duplicate station name — resolved by district "
                               f"({best['district']})")
            elif status == "ambiguous":
                out["method"] = (f"{kind} match on Police Station "
                                 f"(score: {best['score']}%) | duplicate station name "
                                 f"in {len(hits)} districts — select the correct record")
                out["note"] = (
                    f"duplicate station name '{best['police_station']}' exists in "
                    f"{len(hits)} districts: "
                    + ", ".join(h["district"] for h in hits)
                    + " — select the correct record"
                )
            return out

        print(f"\n  [WARN] '{known_ps}' not found in Excel (threshold: {FUZZY_CUTOFF}%).")
        print(f"         Trying district/address...\n")

    # ── CASE 2: Known District ────────────────────────────────────────────────
    # Fuzzy-match the district → geocode address → real distance to each PS.
    if known_district.strip():
        hits = find_district_in_excel(known_district, df)

        if hits:
            matched_dist   = hits[0]["district"]
            ps_in_district = df[df[COL_DISTRICT] == matched_dist]
            ps_list        = ps_in_district[COL_PS].tolist()

            # ── Text-first pin ────────────────────────────────────────────────
            # Before distance ranking, check whether the address text itself
            # names a Police Station *within this matched district*. The scan is
            # restricted to ps_in_district, so a same-named PS in another
            # district can never be pinned, and the matcher's own invariants
            # (LOCALITY_CUTOFF + mass-tie rule) still gate the hit. A survivor is
            # pinned at rank 1 with its text-match confidence; the geodesic
            # ranking below then fills the remaining slots. With no text hit,
            # Case 2 is unchanged — pure distance ranking.
            pinned = None
            if address.strip():
                text_hits = find_ps_by_localities(address, ps_in_district)
                if text_hits:
                    pinned = text_hits[0]

            if address.strip():
                ranked = rank_ps_by_distance(address, ps_list, matched_dist)
            else:
                # No address — return first N without distance ranking
                ranked = [
                    {"police_station": ps, "district": matched_dist,
                     "distance": "N/A", "resolved_address": ""}
                    for ps in ps_list[:TOP_N]
                ]

            # Stations skipped by the ranking because they have no cached
            # coordinates (missing or FAILED). Plain lists (e.g. test mocks)
            # simply yield [].
            excluded = getattr(ranked, "excluded", [])

            # ── Honest fallback: distance ranking unavailable ─────────────────
            # The address was given but produced no ranked stations (input
            # geocode failed, or no station in this district has cached
            # coordinates). Never return HIGH confidence with an empty or
            # silently truncated list — return the district's stations
            # unranked and say exactly why.
            if address.strip() and not ranked:
                if pinned:
                    pin_name  = pinned["police_station"]
                    unranked  = [pin_name] + [ps for ps in ps_list if ps != pin_name]
                else:
                    unranked  = ps_list

                results = []
                for i, ps in enumerate(unranked[:TOP_N]):
                    entry = {
                        "rank":             i + 1,
                        "police_station":   ps,
                        "district":         matched_dist,
                        "confidence":       ("HIGH" if pinned["score"] >= 95 else "MEDIUM")
                                            if (pinned and i == 0) else "LOW",
                        "distance":         "N/A",
                        "resolved_address": "",
                    }
                    if pinned and i == 0:
                        entry["match_score"] = pinned["score"]
                    results.append(entry)

                out = {
                    "case":       2,
                    "confidence": "LOW",
                    "method":     (
                        f"District matched: {matched_dist} ({hits[0]['score']}%) | "
                        f"distance ranking unavailable (address could not be geocoded "
                        f"or no cached station coordinates) — stations listed unranked"
                        + (f" | Locality match: {pinned['police_station']} pinned rank 1"
                           if pinned else "")
                    ),
                    "results":    results,
                }
                if excluded:
                    out["note"] = (
                        f"{len(excluded)} station(s) in {matched_dist} excluded from "
                        f"distance ranking (missing/FAILED in coordinate cache): "
                        + ", ".join(excluded)
                    )
                return out

            # Order = [pinned PS] + [distance-ranked, pinned excluded]. Nothing
            # is dropped except by the TOP_N cap, which the pin always survives.
            if pinned:
                pinned_ps = pinned["police_station"]
                dist_row  = next(
                    (r for r in ranked if r["police_station"] == pinned_ps), None)
                head = {
                    "police_station":   pinned_ps,
                    "district":         matched_dist,
                    "distance":         dist_row["distance"] if dist_row else "N/A",
                    "resolved_address": dist_row["resolved_address"] if dist_row else "",
                    "match_score":      pinned["score"],
                }
                tail    = [r for r in ranked if r["police_station"] != pinned_ps]
                ordered = [head] + tail
            else:
                ordered = ranked

            results = []
            for i, item in enumerate(ordered[:TOP_N]):
                if i == 0:
                    confidence = ("HIGH" if pinned["score"] >= 95 else "MEDIUM") \
                                 if pinned else "HIGH"
                else:
                    confidence = "MEDIUM"
                entry = {
                    "rank":             i + 1,
                    "police_station":   item["police_station"],
                    "district":         item.get("district", matched_dist),
                    "confidence":       confidence,
                    "distance":         item.get("distance", "N/A"),
                    "resolved_address": item.get("resolved_address", ""),
                }
                if "match_score" in item:
                    entry["match_score"] = item["match_score"]
                results.append(entry)

            if pinned:
                method = (
                    f"District matched: {matched_dist} ({hits[0]['score']}%) | "
                    f"Locality match: {pinned['police_station']} pinned rank 1 | "
                    f"remaining ranked by geodesic distance"
                )
            else:
                method = (
                    f"District matched: {matched_dist} ({hits[0]['score']}%) | "
                    + ("Ranked by geodesic distance" if address.strip()
                       else "no address — first N returned")
                )

            out = {
                "case":       2,
                "confidence": "HIGH",
                "method":     method,
                "results":    results,
            }

            if excluded:
                out["note"] = (
                    f"{len(excluded)} station(s) in {matched_dist} excluded from "
                    f"distance ranking (missing/FAILED in coordinate cache): "
                    + ", ".join(excluded)
                )

            # Sanity check (insight only — changes no routing, ranking or
            # results). The user asserted this district; if even its nearest PS
            # is implausibly far from the geocoded address, the assertion is
            # probably wrong. We say so and let the human decide — searching
            # other districts here would cost API calls nobody asked for.
            if address.strip() and ranked:
                nearest_km = ranked[0].get("distance_km")
                if nearest_km is not None and nearest_km > DISTANCE_WARN_KM:
                    out["warning"] = (
                        f"Nearest PS in {matched_dist} is {round(nearest_km, 1)} km away "
                        f"— the stated district may not be correct. Consider re-running "
                        f"with address only to let the locality scan / AI check other "
                        f"districts."
                    )

            return out

        print(f"\n  [WARN] District '{known_district}' not found in Excel.")
        print(f"         Falling back to address-only reasoning...\n")

    # ── CASE 3: Address only ──────────────────────────────────────────────────
    # Walks the ladder: locality scan (free) → geocoding → AI (last resort).
    if address.strip():

        # 3a — Deterministic locality scan: does the address itself name a
        #      Police Station? (e.g. 'OLD BOWENPALLY' → 'BOWENPALLY PS')
        #      Excel is the source of truth, so this is tried before spending
        #      a single geocode or AI call.
        ps_hits = find_ps_by_localities(address, df)
        if ps_hits:
            results = [{
                "rank":             i + 1,
                "police_station":   h["police_station"],
                "district":         h["district"],
                "confidence":       "HIGH" if h["score"] >= 95 else "MEDIUM",
                "match_score":      h["score"],
                "distance":         "N/A",
                "resolved_address": "",
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
        #      zone (e.g. 'SECUNDERABAD'). Narrow to it and hand straight to the
        #      geocoding rung — the district is known, so AI is not needed.
        dist_hits = find_district_by_localities(address, df)
        if dist_hits:
            matched_dist = dist_hits[0]["district"]
            ps_list      = df[df[COL_DISTRICT] == matched_dist][COL_PS].tolist()
            ranked       = rank_ps_by_distance(address, ps_list, matched_dist)

            if ranked:
                results = [{
                    "rank":             i + 1,
                    "police_station":   r["police_station"],
                    "district":         r["district"],
                    "confidence":       "HIGH" if i == 0 else "MEDIUM",
                    "distance":         r.get("distance", "N/A"),
                    "resolved_address": r.get("resolved_address", ""),
                } for i, r in enumerate(ranked)]

                out = {
                    "case":       3,
                    "confidence": "MEDIUM",
                    "method":     f"Locality '{dist_hits[0]['locality']}' from address matched "
                                  f"District: {matched_dist} ({dist_hits[0]['score']}%) | "
                                  f"Ranked by geodesic distance",
                    "results":    results,
                }
                excluded = getattr(ranked, "excluded", [])
                if excluded:
                    out["note"] = (
                        f"{len(excluded)} station(s) in {matched_dist} excluded from "
                        f"distance ranking (missing/FAILED in coordinate cache): "
                        + ", ".join(excluded)
                    )
                return out

        # 3c — AI reasoning (last resort): nothing in the Excel matched the
        #      address, so infer the district, then rank by real distance.
        inferred_districts = ai_infer_district(address, df, ai_client)

        all_results  = []
        all_excluded = []

        for district in inferred_districts[:2]:    # at most 2 districts
            ps_list = df[df[COL_DISTRICT] == district][COL_PS].tolist()
            ranked  = rank_ps_by_distance(address, ps_list, district, top_n=2)
            all_excluded.extend(getattr(ranked, "excluded", []))

            for i, r in enumerate(ranked):
                all_results.append({
                    "police_station":   r["police_station"],
                    "district":         r["district"],
                    "confidence":       "MEDIUM" if i == 0 else "LOW",
                    "distance":         r.get("distance", "N/A"),
                    "resolved_address": r.get("resolved_address", ""),
                })

        if all_results:
            for i, r in enumerate(all_results[:TOP_N]):
                r["rank"] = i + 1
            out = {
                "case":       3,
                "confidence": "MEDIUM",
                "method":     (
                    f"AI inferred district | Ranked by geodesic distance | "
                    f"provider: {AI_PROVIDER} | model: {AI_MODEL}"
                ),
                "results": all_results[:TOP_N],
            }
            if all_excluded:
                out["note"] = (
                    f"{len(all_excluded)} station(s) excluded from distance ranking "
                    f"(missing/FAILED in coordinate cache): " + ", ".join(all_excluded)
                )
            return out

    # ── CASE 0: Nothing worked ────────────────────────────────────────────────
    return {
        "case":       0,
        "confidence": "NONE",
        "method":     "Could not determine a match",
        "results":    [],
    }
