"""
GeoSense — matcher.py
----------------------
Fuzzy matching helpers for Police Station and District lookups.
All matching is done locally against the Excel — no AI, no network.

This file has two distinct layers, kept deliberately separate:

  1. NAME LOOKUP (score_match, find_ps_in_excel, find_district_in_excel)
     Used when the user *typed* a Police Station or District name (Case 1 / 2).
     The input is intentional, so matching is lenient.

  2. ADDRESS-LOCALITY SCAN (locality_score, find_ps_by_localities,
     find_district_by_localities)
     Used when only a free-form address is available (rungs 3a / 3b). The
     input is noisy — door numbers, plot numbers, generic suffixes — so this
     layer is strict and is governed by four invariants (see below). Its job
     is to fire ONLY when the address genuinely names a Police Station or
     District, and otherwise to return nothing so the query falls through to
     the AI rung (3c). It must never manufacture a match out of a junk token.

     LOCALITY-SCAN INVARIANTS
     ------------------------
     I1. Minimum signal.  No candidate — lone word or joined segment — shorter
         than MIN_LOCALITY_LEN significant characters may ever be scored.
         Enforced once, at the single exit of extract_localities().
     I2. Evidence, not fragments.  A candidate cannot reach the cutoff merely
         by being a substring of a longer name. locality_score() drops the
         unscaled substring reward that let "NAGAR" score 90 against every
         "*NAGAR" station; whole-name / full-segment agreement always wins.
     I3. A mass tie is a null result.  If more than MAX_TIE_WIDTH candidates
         tie at the top score, the scan returns [] — that width is the
         signature of a token that matches everything.
     I4. Sheet order decides nothing.  Ties inside MAX_TIE_WIDTH break on
         explicit specificity, ending in an alphabetical tiebreak. Excel row
         position has zero influence on the result.
"""

import re

from rapidfuzz import fuzz

from common.config import (
    COL_PS,
    COL_DISTRICT,
    FUZZY_CUTOFF,
    LOCALITY_CUTOFF,
    MIN_LOCALITY_LEN,
    MAX_TIE_WIDTH,
)


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


# ─────────────────────────────────────────────────────────────────────────────
# TEXT NORMALISATION (shared by both layers)
# ─────────────────────────────────────────────────────────────────────────────

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


def _normalize(text):
    """Uppercase, strip PS noise words, and fold hyphens to spaces so that
    'MALKAJGIRI-RANGAREDDY' and 'MALKAJGIRI RANGAREDDY' compare as identical
    — applied identically to address tokens and Excel PS/District names."""
    text = strip_ps_noise(text).replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1 — NAME LOOKUP  (lenient; user typed the name — Case 1 / Case 2)
# ─────────────────────────────────────────────────────────────────────────────

def _scaled_partial_ratio(a, b):
    """
    partial_ratio() scores a full substring match as 100 regardless of how
    much shorter the query is than the candidate — so a lone generic
    fragment like 'NAGAR' scores 100 against every '*NAGAR' Police Station,
    tying (or beating) a real full-segment match. Scale the raw score by
    how much of the longer string the shorter one actually covers, so a
    near-full-length match stays close to 100 while a short fragment buried
    in a long name is scored down proportionally.
    """
    raw = fuzz.partial_ratio(a, b)
    shorter, longer = sorted((len(a), len(b)))
    if longer == 0:
        return 0.0
    return raw * (shorter / longer)


def score_match(query, candidate):
    """
    Score how well a user-typed name matches a candidate (Case 1 / Case 2).

    Runs three RapidFuzz methods and returns the best score. This is the
    LENIENT scorer: the user deliberately typed a Police Station or District
    name, possibly partial or misspelt, so substring help (WRatio) is wanted.
    The address-locality scan uses locality_score() instead — see below.

      WRatio           — handles insertions, deletions, transpositions
      token_sort_ratio — handles word-order differences
      partial_ratio    — handles partial / substring matches (coverage-scaled)
    """
    a = _normalize(query)
    b = _normalize(candidate)
    return max(
        fuzz.WRatio(a, b),
        fuzz.token_sort_ratio(a, b),
        _scaled_partial_ratio(a, b),
    )


def find_ps_in_excel(query, df, district=None):
    """
    Search all Police Stations in the DataFrame for a query string.

    THE LOOKUP KEY IS (DISTRICT, POLICE STATION) — never the station name on
    its own. Station names legitimately repeat across districts (15 names in
    the Telangana master, one of them three times); those are valid, distinct
    records, verified against the official master. Each matching
    (district, station) pair is therefore returned as its own result. A
    duplicated name is never collapsed to whichever row happens to sit first
    in the sheet.

    `district`, when supplied, restricts the search to that district. It
    disambiguates between equally valid records — it does not override
    PS-first priority, and it never invents a match. If it matches none of
    the rows, the caller receives every valid pair and can present them for
    selection rather than being handed an arbitrary one.

    Returns a list of dicts sorted best-score first, ties broken
    alphabetically by district so ordering never depends on sheet position
    (invariant I4).
    Each dict: { police_station, district, score }
    """
    want = _normalize(district) if district and str(district).strip() else None

    results = []
    seen    = set()

    for _, row in df.iterrows():
        ps   = row[COL_PS]
        dist = row[COL_DISTRICT]

        key = (dist, ps)                    # composite key, not the name alone
        if key in seen:
            continue
        seen.add(key)

        if want is not None and _normalize(dist) != want:
            continue

        s = score_match(query, ps)
        if s >= FUZZY_CUTOFF:
            results.append({
                "police_station": ps,
                "district":       dist,
                "score":          round(s, 1),
            })

    return sorted(results, key=lambda x: (-x["score"], x["district"]))


def resolve_ps_with_district(query, df, district=None):
    """
    Case-1 resolution for a user-typed Police Station name, honouring the
    composite (DISTRICT, POLICE STATION) key.

    Returns (hits, status), where status is one of:

      'none'                 — nothing cleared FUZZY_CUTOFF
      'unique'               — the best-matching name exists in exactly one
                               district. `district` is not consulted at all:
                               PS-first priority stands, and behaviour is
                               unchanged from before the composite key.
      'resolved_by_district' — the name exists in several districts and the
                               supplied district selected exactly one of them
      'ambiguous'            — the name exists in several districts and no
                               district was supplied, or the supplied one
                               matched none of them. Every valid record is
                               returned so the caller can present them for
                               selection. Nothing is auto-picked, and sheet
                               order is never the tiebreak.

    A supplied district disambiguates between equally valid records; it never
    overrides PS-first priority and never suppresses a unique match.
    """
    hits = find_ps_in_excel(query, df)
    if not hits:
        return [], "none"

    top_name  = hits[0]["police_station"]
    top_group = [h for h in hits if h["police_station"] == top_name]

    if len(top_group) == 1:
        return [hits[0]], "unique"

    if district and str(district).strip():
        want     = _normalize(district)
        selected = [h for h in top_group if _normalize(h["district"]) == want]
        if len(selected) == 1:
            return selected, "resolved_by_district"
        # Supplied district matched none (or several) of the valid rows —
        # fall through and show them all rather than guessing.

    return top_group, "ambiguous"


def find_district_in_excel(query, df):
    """
    Search all Districts in the DataFrame for a query string.
    Returns a list of dicts sorted best-score first.
    Each dict: { district, score }

    An exact (case-insensitive) match is preferred and returned immediately.
    This prevents a shorter district name from tying the true match on
    fuzzy score — e.g. 'WARANGAL' scoring 100 (as a substring) against a
    query of 'WARANGAL-HANUMAKONDA'. Only when no exact match exists does
    the fuzzy fallback below run.
    """
    all_districts = df[COL_DISTRICT].unique().tolist()

    q = query.strip().upper()
    for d in all_districts:
        if str(d).strip().upper() == q:
            return [{"district": d, "score": 100.0}]

    results = []

    for d in all_districts:
        s = score_match(query, d)
        if s >= FUZZY_CUTOFF:
            results.append({"district": d, "score": round(s, 1)})

    return sorted(results, key=lambda x: x["score"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2 — ADDRESS-LOCALITY SCAN  (strict; only an address is available)
# ─────────────────────────────────────────────────────────────────────────────

def _significant_len(candidate):
    """Number of alphabetic characters in a candidate, ignoring the spaces
    that join a multi-word segment. 'LB NAGAR' → 7, 'H' → 1. This is the
    single measure used to enforce invariant I1 (minimum signal)."""
    return len(candidate.replace(" ", ""))


def _segment_words(segment):
    """Split one address segment into significant words: drop digits, symbols,
    door numbers, and address-structure stopwords. Short words are NOT dropped
    here — the length gate is applied once, uniformly, in extract_localities()."""
    return [w for w in re.split(r"[^A-Z]+", segment) if w and w not in ADDR_STOPWORDS]


def extract_localities(address):
    """
    Pull candidate locality names out of a free-form address.

    Each comma/slash segment yields two kinds of candidate:
      - its cleaned multi-word form   ('SAI BABA NAGAR')
      - each of its individual words  ('SAI', 'BABA', 'NAGAR')

    INVARIANT I1 (minimum signal) is enforced at the SINGLE exit point below:
    every candidate — joined segment or lone word, now or in future — must
    pass through the same MIN_LOCALITY_LEN gate. There is deliberately no
    per-branch length check, so no path can bypass the gate. This is what
    stops a door-number fragment such as 'H' (from 'H NO 5-2-88') from ever
    becoming a candidate.

    Example:
        '6-31-1,FLAT NO:101,AKHILA ENCLAVE,OLD BOWENPALLY,SECUNDERABAD,pin:500011'
        → ['AKHILA', 'BOWENPALLY', 'SECUNDERABAD', ...]
    """
    text       = address.upper()
    candidates = []

    for seg in re.split(r"[,\n;|/]+", text):
        words = _segment_words(seg)
        if not words:
            continue
        candidates.append(" ".join(words))   # multi-word segment
        candidates.extend(words)             # each individual word

    # ── Single, uniform minimum-signal gate (invariant I1) ────────────────────
    candidates = [c for c in candidates if _significant_len(c) >= MIN_LOCALITY_LEN]

    # de-duplicate, preserve first-seen order
    return list(dict.fromkeys(candidates))


def locality_score(token, candidate):
    """
    Score an address-derived token against an Excel Police Station / District
    name. This is the STRICT scorer, and the heart of invariant I2.

    WHY IT DIFFERS FROM score_match
    -------------------------------
    The fragment-domination failure came from substring rewards. RapidFuzz's
    WRatio (and raw partial_ratio) return ~90–100 whenever the token is a
    substring of the candidate, *independent of length*: 'NAGAR' scored 90
    against SUJATHANAGAR, BALANAGAR, CHANDANAGAR … and against 50+ others, all
    tied, so the real answer could only win by luck (or lose to sheet order).

    locality_score() removes that reward. It combines only two length-aware
    measures and takes the larger:

      token_sort_ratio(a, b)       — symmetric character agreement over the
        WHOLE of both strings. Every character of the longer name that the
        token fails to cover pulls the score down, so a short fragment against
        a long name scores low by construction (NAGAR/SUJATHANAGAR ≈ 59).

      _scaled_partial_ratio(a, b)  — best-substring alignment, but multiplied
        by coverage (shorter/longer), so a fragment buried in a long name is
        discounted in proportion to how little of it it covers (≈ 42 there).

    Consequences:
      - A whole-segment or whole-name agreement scores ~100 and always
        outranks any fragment match.
      - A generic suffix like 'NAGAR' can no longer reach LOCALITY_CUTOFF on
        substring containment alone — it must actually resemble the full name.
    Together these make fragment domination impossible rather than merely
    unlikely.
    """
    a = _normalize(token)
    b = _normalize(candidate)
    return max(
        fuzz.token_sort_ratio(a, b),
        _scaled_partial_ratio(a, b),
    )


def _specificity_key(hit, name_key):
    """
    Deterministic ranking key for locality-scan hits (invariant I4).

    Ordered by descending priority; Excel row position is never consulted:
      1. score            — higher is better
      2. match completeness — a hit found via a fuller, multi-word candidate
                              ('LB NAGAR', 2 words) outranks one found via a
                              single split-out fragment ('MALKAJGIRI', 1 word)
      3. candidate length — a longer matching candidate is more specific
      4. name (A→Z)       — deterministic alphabetical tiebreak
      5. district (A→Z)   — final tiebreak for a station name that legitimately
                            repeats across districts. Without it two valid
                            records with the same name tie on every earlier
                            key, and their order would fall back to dict
                            insertion — i.e. sheet order, the exact thing
                            invariant I4 forbids.

    Returned as a tuple usable directly with sorted(): the first three are
    negated so that larger = earlier; name and district sort ascending.
    """
    return (
        -hit["score"],
        -len(hit["locality"].split()),
        -len(hit["locality"]),
        hit[name_key],
        hit.get("district") or "",
    )


def _mass_tie(ranked):
    """
    Invariant I3: is the top-score group wider than MAX_TIE_WIDTH?

    `ranked` must already be sorted best-first. A tie this wide means the
    winning token matched a large set of names indiscriminately — a junk
    token — so the caller returns [] and lets the query fall through.
    """
    if not ranked:
        return False
    top = ranked[0]["score"]
    return sum(1 for h in ranked if h["score"] == top) > MAX_TIE_WIDTH


def _best_by_locality(names_with_district, localities, cutoff):
    """
    Score every (name, district) pair against every locality token, keeping
    the single best-scoring locality per name that clears `cutoff`.

    `names_with_district` is an iterable of (name, district) tuples; district
    may be None for the District scan.

    KEYED ON (name, district), not name alone. A station name that repeats
    across districts is a set of distinct valid records, so each one competes
    and survives on its own merit. Keying on the name would silently discard
    every occurrence after the first — the same defect as collapsing the
    lookup key, one layer down.

    Returns a dict:
        (name, district) -> {score, district, locality}
    """
    best = {}
    for name, district in names_with_district:
        key = (name, district)
        for loc in localities:
            s = locality_score(loc, name)
            if s >= cutoff and s > best.get(key, {}).get("score", 0):
                best[key] = {"score": s, "district": district, "locality": loc}
    return best


def _disambiguate_duplicates_by_text(hits, localities, cutoff):
    """
    Free disambiguation for a station name that exists in several districts.

    When the same station name survives in more than one district, the address
    text itself is often already carrying the answer — '...NAWABPET, POMAL,
    MAHABUBNAGAR...' names both the station and its district. If exactly one
    of the tied districts is named in the address, that record is the intended
    one and the others are dropped.

    This is evidence already in hand, scored with the same strict locality
    scorer and cutoff — no geocoding, no AI, no new inference. If the address
    names none of the districts, or names more than one, nothing is dropped:
    every valid record survives for the caller to present for selection.
    Choosing between known rows is a selection, not a guess.
    """
    by_name = {}
    for h in hits:
        by_name.setdefault(h["police_station"], []).append(h)

    kept = []
    for name, group in by_name.items():
        if len(group) == 1:
            kept.extend(group)
            continue

        supported = [
            h for h in group
            if any(locality_score(loc, h["district"]) >= cutoff for loc in localities)
        ]
        # Exactly one district named in the address → that record wins.
        # Zero or several → keep them all and let the user choose.
        kept.extend(supported if len(supported) == 1 else group)

    return kept


def find_ps_by_localities(address, df, cutoff=LOCALITY_CUTOFF):
    """
    Scan every Police Station name for any locality token from the address.
    Fires only when the address genuinely names a PS area (e.g. 'OLD
    BOWENPALLY' → 'BOWENPALLY PS'); otherwise returns [] so the query falls
    through to 3b / 3c.

    All four invariants apply: candidates are pre-gated for length (I1),
    scored for evidence not substring (I2), a mass top-tie yields [] (I3),
    and remaining ties break on specificity + alphabetical, never sheet
    order (I4).

    Returns a list of dicts sorted best-score first:
        { police_station, district, score, locality }
    """
    localities = extract_localities(address)
    if not localities:
        return []

    # Every (station, district) row competes. The previous
    # drop_duplicates(subset=[COL_PS]) kept whichever row came first in the
    # sheet, letting Excel position decide which district a duplicated station
    # name resolved to — a direct breach of invariant I4. A duplicated name
    # now surfaces once per district as distinct candidates, and the caller
    # decides between them.
    ps_rows = (
        (row[COL_PS], row[COL_DISTRICT])
        for _, row in df.drop_duplicates(subset=[COL_DISTRICT, COL_PS]).iterrows()
    )
    best = _best_by_locality(ps_rows, localities, cutoff)

    hits = [{
        "police_station": name,
        "district":       info["district"],
        "score":          round(info["score"], 1),
        "locality":       info["locality"],
    } for (name, _dist), info in best.items()]

    # A duplicated station name may already be resolved by the address itself.
    # Applied before the mass-tie check so that districts ruled out by the text
    # do not inflate the tie width.
    hits   = _disambiguate_duplicates_by_text(hits, localities, cutoff)
    ranked = sorted(hits, key=lambda h: _specificity_key(h, "police_station"))

    if _mass_tie(ranked):
        return []          # invariant I3 — junk token matched too many stations
    return ranked


def find_district_by_localities(address, df, cutoff=LOCALITY_CUTOFF):
    """
    Scan every District name for any locality token from the address. Used as
    a second pass when the address does not directly name a Police Station but
    does name a district / zone (e.g. 'SECUNDERABAD').

    Same four invariants as find_ps_by_localities().

    Returns a list of dicts sorted best-score first:
        { district, score, locality }
    """
    localities = extract_localities(address)
    if not localities:
        return []

    dist_rows = ((d, None) for d in df[COL_DISTRICT].unique().tolist())
    best = _best_by_locality(dist_rows, localities, cutoff)

    hits = [{
        "district": name,
        "score":    round(info["score"], 1),
        "locality": info["locality"],
    } for (name, _none), info in best.items()]

    ranked = sorted(hits, key=lambda h: _specificity_key(h, "district"))

    if _mass_tie(ranked):
        return []          # invariant I3 — junk token matched too many districts
    return ranked
