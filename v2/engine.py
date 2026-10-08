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
  Case 3n — No state named, 3a/3b empty → nearest stations, all states (1 geocode)
  Case 3c — Address unmatched        → AI infers district → geocode → rank

Before any case runs, find_best_match() narrows the stations to the state the
address names (common/state_filter.py). In 3a the station named in the address
has priority, and one geocode of the address verifies it by distance.
  Case 0  — Nothing worked → empty result

AI is only ever called in Case 3c, and only to infer a district from text.
All distance ranking uses real coordinates from the Geocoding API.
"""

from v2.config import (
    COL_DISTRICT, COL_PS, COL_STATE, TOP_N, FUZZY_CUTOFF,
    DISTANCE_WARN_KM, AI_PROVIDER, AI_MODEL,
    CROSS_DISTRICT_MARGIN_KM, CROSS_DISTRICT_MAX,
)
from common.matcher import (
    find_ps_in_excel,
    resolve_ps_with_district,
    find_district_in_excel,
    find_ps_by_localities,
    find_district_by_localities,
)
from common.state_filter import filter_by_state
from v2.ai_engine import ai_infer_district
from v2.geopy_distance import (
    rank_ps_by_distance, rank_ps_nearby_any_district,
    measure_from_address, geodesic_distance, _load_coords_cache,
)


def find_best_match(address, known_ps, known_district, df, ai_client):
    """
    Narrow the stations to the state the address names, then run the ladder.

    State first, always: station names repeat across states but a person lives
    in one, so a Telangana address is never offered an Andhra Pradesh station.
    With no single state in the address, every state is searched, as before.
    The ladder itself (_find_best_match) is unchanged; it simply sees fewer rows.
    The returned dict gains `state_scope`: which stations were searched, and why.

    Shown stations whose coordinate is shared with a differently named station
    are marked LOW with a warning: the distance cannot tell those apart.
    """
    scoped_df, state_scope, state = filter_by_state(address, df)
    result = _find_best_match(address, known_ps, known_district, scoped_df, ai_client,
                              state_named=state is not None)
    uncertain = [r for r in result.get("results", [])
                 if r.get("coordinate_unverified")]
    if uncertain:
        for row in uncertain:
            row["confidence"] = "LOW"
        if result["results"][0].get("coordinate_unverified"):
            result["confidence"] = "LOW"
        message = (f"{len(uncertain)} shown station coordinate(s) are shared with "
                   "a differently named station. Distances cannot distinguish "
                   "them; confirm jurisdiction independently.")
        result["warning"] = (result.get("warning", "") + " " + message).strip()
    _merge_relisted_stations(result)
    result["state_scope"] = state_scope
    return result


# Two rows with the same station name whose stored points are this close are
# one station listed twice — e.g. Tamil Nadu stations kept under VELLORE and
# under RANIPET / TIRUPATHUR after the 2019 split. Distinct same-name stations
# in the sheet are all 5 km+ apart.
RELISTED_MAX_KM = 0.5


def _merge_relisted_stations(result):
    """
    Show a station listed under two districts once, naming both districts,
    instead of letting it fill two of the shown slots. Presentation only: the
    sheet keeps both rows, and nothing merges without both stored coordinates.
    """
    rows = result.get("results", [])
    if len(rows) < 2:
        return
    coords = _load_coords_cache()
    kept, merged = [], []
    for row in rows:
        point = coords.get((row["district"], row["police_station"]))
        twin = next((k for k in kept
                     if k["police_station"] == row["police_station"]
                     and point and k["_point"]
                     and geodesic_distance(point, k["_point"]) <= RELISTED_MAX_KM), None)
        if twin:
            twin["district"] += f" / {row['district']}"
            merged.append(twin)
            continue
        row["_point"] = point
        kept.append(row)
    for i, row in enumerate(kept, 1):
        row.pop("_point")
        row["rank"] = i
    if merged:
        result["results"] = kept
        note = "; ".join(f"{m['police_station']} is listed under {m['district']} "
                         f"(same station)" for m in merged)
        result["note"] = (result.get("note", "") + " " + note).strip()


def _km_label(km):
    return f"~{round(km, 1)} km" if km is not None else "N/A"


# ── Cross-district neighbours ─────────────────────────────────────────────────
# Any rung that narrows to a single district filters *before* distance is ever
# measured, so a station on the far side of a district line is dropped however
# near it is. That bites whenever the district is loose (a city name spanning
# several districts) or simply wrong: the honest answer can be metres away and
# never gets ranked.
#
# These three helpers are shared by the rungs that narrow this way — Case 2
# (district typed by the user) and Case 3b (district named in the address) — so
# the two cannot drift apart.
#
# Surfaced, never substituted: the matched district's own ranking always stays
# in the list. Nearest in a straight line is not the same as correct
# jurisdiction, so this adds evidence for the officer rather than overriding them.

def _nearer_in_other_districts(address, df, matched, ranked):
    """
    Stations outside the searched district(s) that are clearly nearer than the
    best already found.

    `matched` is one district name, or an iterable of them — Case 3c searches up
    to two AI-inferred districts, and a station in either of those is not a
    neighbour. `ranked` is whatever was found so far, nearest first; only its
    best distance is read.

    Costs no extra API call: station coordinates come from the prebuilt cache
    and the address geocode is memoised, so the second pass reuses the first.

    Returns [] when there is no address, nothing ranked, no distance to compare
    against, or no neighbour beats the margin.
    """
    if not (address.strip() and ranked):
        return []
    best_so_far = ranked[0].get("distance_km")
    if best_so_far is None:
        return []

    nearby  = rank_ps_nearby_any_district(address, df,
                                          top_n=TOP_N + CROSS_DISTRICT_MAX)
    targets = ({str(matched).strip().upper()} if isinstance(matched, str)
               else {str(d).strip().upper() for d in matched})
    return [
        n for n in nearby
        if str(n["district"]).strip().upper() not in targets
        and n.get("distance_km") is not None
        and best_so_far - n["distance_km"] >= CROSS_DISTRICT_MARGIN_KM
    ][:CROSS_DISTRICT_MAX]


def _neighbour_rows(neighbours):
    """Result rows for the neighbours, ranked from 1 — they lead the table."""
    return [{
        "rank":             i + 1,
        "police_station":   n["police_station"],
        "district":         n["district"],
        "confidence":       "MEDIUM",
        "distance":         n.get("distance", "N/A"),
        "resolved_address": n.get("resolved_address", ""),
        "coordinate_unverified": n.get("coordinate_unverified", False),
        "outside_stated_district": True,
    } for i, n in enumerate(neighbours)]


def _neighbour_warning(neighbours, matched_label, ranked, source):
    """
    Say plainly that the lead row is outside the district(s) that were searched,
    and why it is there anyway. Without this the table reads as a filter failure.

    `matched_label` is how to name the searched district(s) in the sentence, and
    `source` names where they came from, so the officer knows whether to question
    their own input, the address text, or the AI's guess.
    """
    near = neighbours[0]
    return (
        f"{near['police_station']} ({near['district']}) is {near['distance']} away "
        f"— nearer than anything in {matched_label}, whose closest is "
        f"{ranked[0]['distance']}. It sits outside the district {source}, so it is "
        f"shown for comparison, not as a correction. District boundaries do not "
        f"follow distance — confirm jurisdiction before using it."
    )


def _find_best_match(address, known_ps, known_district, df, ai_client, state_named=False):
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
                    for ps in sorted(set(ps_list))[:TOP_N]
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
                    "coordinate_unverified": (dist_row.get("coordinate_unverified", False)
                                              if dist_row else False),
                }
                tail    = [r for r in ranked if r["police_station"] != pinned_ps]
                ordered = [head] + tail
            else:
                ordered = ranked

            # Nearer neighbours lead, so the closest station is visible first;
            # the stated district's own ranking follows intact below.
            neighbours = _nearer_in_other_districts(address, df, matched_dist, ranked)
            results    = _neighbour_rows(neighbours)

            for i, item in enumerate(ordered[:TOP_N]):
                if not address.strip():
                    confidence = "LOW"
                elif i == 0:
                    confidence = ("HIGH" if pinned["score"] >= 95 else "MEDIUM") \
                                 if pinned else "HIGH"
                else:
                    confidence = "MEDIUM"
                entry = {
                    "rank":             len(results) + 1,
                    "police_station":   item["police_station"],
                    "district":         item.get("district", matched_dist),
                    "confidence":       confidence,
                    "distance":         item.get("distance", "N/A"),
                    "resolved_address": item.get("resolved_address", ""),
                    "coordinate_unverified": item.get("coordinate_unverified", False),
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
                       else "no address — alphabetical preview, not ranked")
                )

            if neighbours:
                method += (
                    f" | {len(neighbours)} nearer station(s) found outside "
                    f"{matched_dist} — listed first"
                )

            out = {
                "case":       2,
                "confidence": "HIGH" if address.strip() else "LOW",
                "method":     method,
                "results":    results,
            }

            if neighbours:
                out["warning"] = _neighbour_warning(
                    neighbours, matched_dist, ranked, "you entered")

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
            # Only when no nearer neighbour was found: that warning is the more
            # specific finding and already names a concrete alternative, so it
            # must not be overwritten by this general one.
            if address.strip() and ranked and not neighbours:
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
            # The station named in the address has priority — no station the
            # text did not name is ever added here. One geocode of the address
            # then verifies it: text hits are ordered nearest-first (so a
            # duplicate name resolves to the one near the address), and a hit
            # implausibly far away is downgraded and flagged, never dropped.
            # Stable sort: equal / missing distances keep the text order.
            measured = measure_from_address(
                address, [(h["district"], h["police_station"]) for h in ps_hits])
            km = {}
            unverified = {}
            if measured:
                km = {(m["district"], m["police_station"]): m["distance_km"]
                      for m in measured}
                unverified = {(m["district"], m["police_station"]):
                              m.get("coordinate_unverified", False) for m in measured}
                ps_hits = sorted(ps_hits, key=lambda h: (
                    km.get((h["district"], h["police_station"])) is None,
                    km.get((h["district"], h["police_station"])) or 0.0))

            def _km(h):
                return km.get((h["district"], h["police_station"]))

            def _conf(h):
                if unverified.get((h["district"], h["police_station"])):
                    return "LOW"
                if _km(h) is not None and _km(h) > DISTANCE_WARN_KM:
                    return "LOW"
                return "HIGH" if h["score"] >= 95 else "MEDIUM"

            results = [{
                "rank":             i + 1,
                "police_station":   h["police_station"],
                "district":         h["district"],
                "confidence":       _conf(h),
                "match_score":      h["score"],
                "distance":         _km_label(_km(h)),
                "resolved_address": "",
                "coordinate_unverified": unverified.get((h["district"],
                                                        h["police_station"]), False),
            } for i, h in enumerate(ps_hits[:TOP_N])]

            top = ps_hits[0]
            out = {
                "case":       3,
                "confidence": _conf(top),
                "method":     f"Locality '{top['locality']}' from address matched "
                              f"Police Station in Excel (score: {top['score']}%)"
                              + (" | verified by geodesic distance" if measured
                                 else " | distance check unavailable (address not geocoded)"),
                "results":    results,
            }
            if _km(top) is not None and _km(top) > DISTANCE_WARN_KM:
                out["warning"] = (
                    f"{top['police_station']} ({top['district']}) is named in the address "
                    f"but is {round(_km(top), 1)} km from where the address geocodes — "
                    f"check the address or the station before relying on it."
                )
            return out

        # 3b — Locality scan against District column: address names a district /
        #      zone (e.g. 'SECUNDERABAD'). Narrow to it and hand straight to the
        #      geocoding rung — the district is known, so AI is not needed.
        dist_hits = find_district_by_localities(address, df)
        if dist_hits:
            matched_dist = dist_hits[0]["district"]
            ps_list      = df[df[COL_DISTRICT] == matched_dist][COL_PS].tolist()
            ranked       = rank_ps_by_distance(address, ps_list, matched_dist)

            if ranked:
                # Same blind spot as Case 2: narrowing to the district named in
                # the address drops a nearer station just over its boundary
                # before distance is measured. The district came from the text
                # rather than the officer, but it is no less able to be loose —
                # a zone name can read as one district and sit beside another.
                neighbours = _nearer_in_other_districts(address, df, matched_dist, ranked)
                results    = _neighbour_rows(neighbours)

                results += [{
                    "rank":             len(results) + i + 1,
                    "police_station":   r["police_station"],
                    "district":         r["district"],
                    "confidence":       "HIGH" if i == 0 else "MEDIUM",
                    "distance":         r.get("distance", "N/A"),
                    "resolved_address": r.get("resolved_address", ""),
                    "coordinate_unverified": r.get("coordinate_unverified", False),
                } for i, r in enumerate(ranked)]

                method = (f"Locality '{dist_hits[0]['locality']}' from address matched "
                          f"District: {matched_dist} ({dist_hits[0]['score']}%) | "
                          f"Ranked by geodesic distance")
                if neighbours:
                    method += (f" | {len(neighbours)} nearer station(s) found outside "
                               f"{matched_dist} — listed first")

                out = {
                    "case":       3,
                    "confidence": "MEDIUM",
                    "method":     method,
                    "results":    results,
                }
                if neighbours:
                    out["warning"] = _neighbour_warning(
                        neighbours, matched_dist, ranked, "named in the address")
                excluded = getattr(ranked, "excluded", [])
                if excluded:
                    out["note"] = (
                        f"{len(excluded)} station(s) in {matched_dist} excluded from "
                        f"distance ranking (missing/FAILED in coordinate cache): "
                        + ", ".join(excluded)
                    )
                return out

        # 3n — No single state named, and the text named no station or
        #      district: rank every station, in every state, by real distance
        #      from the address. One geocode; station coordinates come from the
        #      sheet. Stations without coordinates are counted, never guessed.
        if not state_named:
            measured = measure_from_address(
                address, list(zip(df[COL_DISTRICT], df[COL_PS])))
            if measured:
                with_km = sorted((m for m in measured if m["distance_km"] is not None),
                                 key=lambda m: (m["distance_km"], m["police_station"],
                                                m["district"]))
                no_km   = len(measured) - len(with_km)
                # All states searched, so each row says which state it is in.
                states   = df[COL_STATE] if COL_STATE in df else [""] * len(df)
                state_of = dict(zip(zip(df[COL_DISTRICT], df[COL_PS]), states))
                if with_km:
                    near = with_km[:TOP_N]
                    out = {
                        "case":       3,
                        "confidence": "MEDIUM",
                        "method":     "State not named in address | nearest stations "
                                      "by geodesic distance, all states",
                        "results": [{
                            "rank":             i + 1,
                            "police_station":   m["police_station"],
                            "district":         m["district"],
                            "state":            state_of.get((m["district"],
                                                              m["police_station"]), ""),
                            "confidence":       "MEDIUM" if i == 0 else "LOW",
                            "distance":         _km_label(m["distance_km"]),
                            "resolved_address": "",
                            "coordinate_unverified": m.get("coordinate_unverified", False),
                        } for i, m in enumerate(near)],
                    }
                    if near[0]["distance_km"] > DISTANCE_WARN_KM:
                        out["warning"] = (
                            f"Nearest station is {round(near[0]['distance_km'], 1)} km "
                            f"away — the address may not have geocoded to the right "
                            f"place. Adding the state name to the address will help."
                        )
                    if no_km:
                        out["note"] = (f"{no_km} station(s) have no coordinates and "
                                       f"were not ranked — run scripts/build_ps_coords.py")
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
                    "coordinate_unverified": r.get("coordinate_unverified", False),
                    "distance_km":      r.get("distance_km"),
                })

        if all_results:
            all_results.sort(key=lambda r: (r.get("distance_km") is None,
                                            r.get("distance_km") or 0.0,
                                            r["police_station"], r["district"]))

            # The same narrowing problem, and here it is at its worst: the
            # districts were guessed by a model, on an address nothing in the
            # sheet could match. If the guess is off, the true station sits in a
            # district that was never searched and cannot appear at all. So
            # measure the whole scope and surface anything clearly nearer than
            # the best of what the AI chose. Both inferred districts count as
            # already-searched, so neither is reported as its own neighbour.
            searched   = [str(d) for d in inferred_districts[:2]]
            neighbours = _nearer_in_other_districts(address, df, searched, all_results)

            results = _neighbour_rows(neighbours) + all_results[:TOP_N]
            for i, r in enumerate(results):
                r["rank"] = i + 1

            method = (f"AI inferred district | Ranked by geodesic distance | "
                      f"provider: {AI_PROVIDER} | model: {AI_MODEL}")
            if neighbours:
                method += (f" | {len(neighbours)} nearer station(s) found outside "
                           f"the inferred district(s) — listed first")

            out = {
                "case":       3,
                "confidence": "MEDIUM",
                "method":     method,
                "results":    results,
            }
            if neighbours:
                out["warning"] = _neighbour_warning(
                    neighbours, " / ".join(searched) or "the inferred district(s)",
                    all_results, "the AI inferred")
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

