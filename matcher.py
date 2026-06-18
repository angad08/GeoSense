"""
GeoSense — matcher.py
----------------------
Fuzzy matching helpers for Police Station and District lookups.
All matching is done locally against the Excel — no AI, no network.
"""

import re

from rapidfuzz import fuzz

from config import COL_PS, COL_DISTRICT, FUZZY_CUTOFF, LOCALITY_CUTOFF


# Address-structure words that are never a locality on their own. Used by the
# locality extractor so that words like FLAT / PLOT / ENCLAVE / TELANGANA are
# not fuzzy-matched against Police Station or District names.
ADDR_STOPWORDS = {
    "FLAT", "PLOT", "DOOR", "ROOM", "FLOOR", "NO", "HNO", "DNO", "SNO",
    "NEAR", "OPP", "OPPOSITE", "BEHIND", "BESIDE", "ABOVE", "BELOW",
    "PIN", "PINCODE", "POST", "DIST", "DISTRICT", "MANDAL", "VILLAGE",
    "STATE", "INDIA", "TELANGANA", "ANDHRA", "PRADESH",
    "ROAD", "STREET", "LANE", "CROSS", "MAIN", "PHASE", "SECTOR",
    "BLOCK", "ENCLAVE", "COLONY", "APARTMENT", "APARTMENTS", "APTS",
    "RESIDENCY", "TOWERS", "TOWER", "HEIGHTS", "HOUSE", "BUILDING",
    "OLD", "NEW",          # too generic to match on their own
}


def strip_ps_noise(text):
    """
    Remove common words that break fuzzy matching.

    Examples:
        'PS SADAR'                  → 'SADAR'
        'GACHIBOWLI POLICE STATION' → 'GACHIBOWLI'
        'MADHAPUR'                  → 'MADHAPUR'  (no change)
    """
    text = text.strip().upper()
    text = re.sub(r"^(POLICE\s*STATION|P\.?\s*S\.?|THANA|CHOWKI)\s+", "", text)
    text = re.sub(r"\s+(POLICE\s*STATION|P\.?\s*S\.?|THANA|CHOWKI)$",  "", text)
    return text.strip()


def score_match(query, candidate):
    """
    Score how well query matches candidate.
    Runs three RapidFuzz methods and returns the best score.

      WRatio           — handles insertions, deletions, transpositions
      token_sort_ratio — handles word-order differences
      partial_ratio    — handles partial / substring matches
    """
    a = strip_ps_noise(query)
    b = strip_ps_noise(candidate)
    return max(
        fuzz.WRatio(a, b),
        fuzz.token_sort_ratio(a, b),
        fuzz.partial_ratio(a, b),
    )


def find_ps_in_excel(query, df):
    """
    Search all Police Stations in the DataFrame for a query string.
    Returns a list of dicts sorted best-score first.
    Each dict: { police_station, district, score }
    """
    results = []
    seen    = set()

    for _, row in df.iterrows():
        ps = row[COL_PS]
        if ps in seen:
            continue
        seen.add(ps)

        s = score_match(query, ps)
        if s >= FUZZY_CUTOFF:
            results.append({
                "police_station": ps,
                "district":       row[COL_DISTRICT],
                "score":          round(s, 1),
            })

    return sorted(results, key=lambda x: x["score"], reverse=True)


def find_district_in_excel(query, df):
    """
    Search all Districts in the DataFrame for a query string.
    Returns a list of dicts sorted best-score first.
    Each dict: { district, score }
    """
    all_districts = df[COL_DISTRICT].unique().tolist()
    results       = []

    for d in all_districts:
        s = score_match(query, d)
        if s >= FUZZY_CUTOFF:
            results.append({"district": d, "score": round(s, 1)})

    return sorted(results, key=lambda x: x["score"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# ADDRESS-LOCALITY SCAN (used when neither PS nor District is supplied)
# ─────────────────────────────────────────────────────────────────────────────

def extract_localities(address):
    """
    Pull candidate locality names out of a free-form address.

    Door numbers, flat/plot numbers, PIN codes, state names and other
    address-structure noise are dropped. Each comma segment yields its cleaned
    multi-word form plus its individual significant words, so that:

        '6-31-1,FLAT NO:101,PLOT NO:69,AKHILA ENCLAVE,OLD BOWENPALLY,
         SECUNDERABAD,telangana,pin:500011'

    produces candidates like:  ['AKHILA', 'BOWENPALLY', 'SECUNDERABAD']

    These are then fuzzy-matched against the Police Station and District columns.
    """
    text       = address.upper()
    segments   = re.split(r"[,\n;|/]+", text)
    localities = []

    for seg in segments:
        words = []
        # split on anything non-alphabetic → drops digits, ':', '-', door nos.
        for w in re.split(r"[^A-Z]+", seg):
            if not w or w in ADDR_STOPWORDS or len(w) < 4:
                continue
            words.append(w)

        if not words:
            continue

        localities.append(" ".join(words))   # cleaned multi-word locality
        localities.extend(words)              # and each significant word alone

    # de-duplicate, preserve order
    return list(dict.fromkeys(localities))


def find_ps_by_localities(address, df, cutoff=LOCALITY_CUTOFF):
    """
    Scan every Police Station name for any locality token taken from the
    address. Catches cases where the address itself names the PS area
    (e.g. 'OLD BOWENPALLY' → 'BOWENPALLY PS') even though no PS/District was
    given by the user.

    Returns a list of dicts sorted best-score first:
        { police_station, district, score, locality }
    """
    localities = extract_localities(address)
    if not localities:
        return []

    best = {}   # police_station -> {score, district, locality}

    for _, row in df.drop_duplicates(subset=[COL_PS]).iterrows():
        ps   = row[COL_PS]
        dist = row[COL_DISTRICT]
        for loc in localities:
            s = score_match(loc, ps)
            if s >= cutoff and s > best.get(ps, {}).get("score", 0):
                best[ps] = {"score": s, "district": dist, "locality": loc}

    results = [{
        "police_station": ps,
        "district":       info["district"],
        "score":          round(info["score"], 1),
        "locality":       info["locality"],
    } for ps, info in best.items()]

    return sorted(results, key=lambda x: x["score"], reverse=True)


def find_district_by_localities(address, df, cutoff=LOCALITY_CUTOFF):
    """
    Scan every District name for any locality token taken from the address.
    Used as a second pass when the address does not directly name a Police
    Station but does name a district/zone (e.g. 'SECUNDERABAD').

    Returns a list of dicts sorted best-score first:
        { district, score, locality }
    """
    localities = extract_localities(address)
    if not localities:
        return []

    best = {}   # district -> {score, locality}

    for d in df[COL_DISTRICT].unique().tolist():
        for loc in localities:
            s = score_match(loc, d)
            if s >= cutoff and s > best.get(d, {}).get("score", 0):
                best[d] = {"score": s, "locality": loc}

    results = [{
        "district": d,
        "score":    round(info["score"], 1),
        "locality": info["locality"],
    } for d, info in best.items()]

    return sorted(results, key=lambda x: x["score"], reverse=True)
