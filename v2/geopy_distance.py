"""
GeoSense — geopy_distance.py
-----------------------------
Geocoding and distance calculation.

  geocode_address()     — address string → (lat, lng)
  geodesic_distance()   — (lat, lng) pair → distance in chosen unit
  rank_ps_by_distance() — address + PS list → top N sorted by real distance

geopy.distance.geodesic uses Karney's algorithm on the WGS-84 ellipsoid,
which models Earth's actual (slightly flattened) shape — more accurate than
haversine, which assumes a perfect sphere.

Install dependencies:
    pip install geopy googlemaps
"""

import re
from functools import lru_cache
from pathlib import Path

import openpyxl
from geopy.distance import geodesic
from rapidfuzz import fuzz

from common.api_keys import get_key
from common.matcher import strip_ps_noise
from v2.config import (
    TOP_N, EXCEL_FILE, SHEET_NAME, COL_DISTRICT, COL_PS, COL_STATE,
    COL_LAT, COL_LNG, GEOCODE_COUNTRY, STATE_MATCH_CUTOFF, SEARCH_ALIAS_FILE,
    SIBLING_MAX_KM, SIBLING_MIN_COUNT, STATION_PLACE_MATCH,
    COORD_LAT_MIN, COORD_LAT_MAX, COORD_LNG_MIN, COORD_LNG_MAX,
)


# ─────────────────────────────────────────────────────────────────────────────
# LAZY CLIENT
# ─────────────────────────────────────────────────────────────────────────────

_gmaps = None


def _client():
    """
    Build the Google Maps client on first use, then reuse it.

    Deferred for the same reason as ai_engine.LazyAgent: the fuzzy and locality
    rungs of the ladder answer many lookups without geocoding anything, and a
    client built at import time would demand GOOGLE_MAPS_API_KEY on runs that
    never make a single Maps call. get_key() raises here — at the first real
    geocode — instead of at import.
    """
    global _gmaps
    if _gmaps is None:
        import googlemaps
        _gmaps = googlemaps.Client(key=get_key("GOOGLE_MAPS_API_KEY"))
    return _gmaps


# ─────────────────────────────────────────────────────────────────────────────
# GEOCODING
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=256)
def _geocode_top(address):
    """
    The top Google geocode result (the raw dict) for `address`, or None.

    Never raises on API trouble: quota, timeout, transport and API errors are
    caught and reported as None, so the caller falls through the case ladder
    or returns an honest empty result instead of crashing.

    Memoised per address so one lookup costs one API call even when the address
    is ranked more than once — the district pass and the cross-district pass in
    Case 2 both geocode the same string. The same address always resolves to the
    same point, so reusing it changes no result; it only avoids paying twice.
    """
    try:
        # components= is a hard filter, not a hint: Google answers inside
        # GEOCODE_COUNTRY or returns nothing. language="en" pins the names in
        # the result to English: without it Google sometimes answers in the
        # local script ("தமிழ் நாடு"), which the same-state check cannot match.
        result = _client().geocode(address, components={"country": GEOCODE_COUNTRY},
                                   language="en")
    except Exception as e:
        print(f"  [WARN] Geocoding API error for '{address}': {e}")
        return None
    return result[0] if result else None


def _coords_and_formatted(top):
    location = top["geometry"]["location"]
    return (location["lat"], location["lng"]), top["formatted_address"]


def geocode_address(address, expected_state=None, return_state=False):
    """
    Convert an address string to ((lat, lng), formatted_address).
    Returns None if Google couldn't resolve it.

    Always check the returned formatted_address before trusting the
    coordinates — Google can silently snap to the wrong locality.

    Google's best result is accepted as-is, as the lookup ladder has always
    done: a PIN or precision mismatch is not grounds for discarding it (a
    neighbouring PIN on an exact street match is common), and the ladder's
    own checks (DISTANCE_WARN_KM warnings, the text pin) judge the result.
    `expected_state` is accepted for call compatibility and not enforced here
    — the state filter has already narrowed the stations.
    """
    top = _geocode_top(address)
    if not top:
        return None
    coords, formatted = _coords_and_formatted(top)
    if not return_state:
        return coords, formatted
    google_state = result_state(top)
    if google_state and not google_state.isascii():
        google_state = _english_state_at(*coords) or google_state
    return coords, formatted, google_state


# Result types that mean Google did not find the station and fell back to the
# centre of a whole area: state, district or taluk/tehsil. Such a point can be
# tens of km off while still passing the same-state check, so it is rejected.
# A locality / neighbourhood / POI result is accepted — stations are named for
# the locality they sit in.
VAGUE_RESULT_TYPES = {
    "country",
    "administrative_area_level_1",
    "administrative_area_level_2",
    "administrative_area_level_3",
}


def vague_result_type(top):
    """The area type if `top` is only a state/district/taluk centre, else ""."""
    types = set(top.get("types", []))
    hit = types & VAGUE_RESULT_TYPES
    return sorted(hit)[0] if hit else ""


def result_state(top):
    """The state Google placed a result in (administrative_area_level_1), or ""."""
    for comp in top.get("address_components", []):
        if "administrative_area_level_1" in comp.get("types", []):
            return comp.get("long_name", "")
    return ""


def _english_state_at(lat, lng):
    """
    The state at (lat, lng), in English, by reverse geocoding. Used only when a
    forward result names its state in a local script ("தமிழ் நாடு"): some
    places are stored by Google in the local language only, and language="en"
    does not translate them. "" on any failure.
    """
    try:
        results = _client().reverse_geocode((lat, lng), language="en",
                                            result_type="administrative_area_level_1")
    except Exception as e:
        print(f"  [WARN] Reverse geocoding failed for ({lat}, {lng}): {e}")
        return ""
    for top in results or []:
        state = result_state(top)
        if state.isascii():
            return state
    return ""


def _norm_state(name):
    name = str(name).upper().replace("&", " AND ")
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", name).split())


def same_state(sheet_state, google_state):
    """
    True if Google's state name matches the sheet's STATE cell. Token-set
    fuzzy, so spelling and wording differences pass ("JAMMU & KASHMIR" vs
    "Jammu and Kashmir", "DELHI" vs "NCT of Delhi") — no per-state list.
    """
    a, b = _norm_state(sheet_state), _norm_state(google_state)
    return bool(a and b) and fuzz.token_set_ratio(a, b) >= STATE_MATCH_CUTOFF


def result_district(top):
    """Google's district for a result (level_3 in India, else level_2), or ""."""
    comps = top.get("address_components", [])
    for level in ("administrative_area_level_3", "administrative_area_level_2"):
        for comp in comps:
            if level in comp.get("types", []):
                return comp.get("long_name", "")
    return ""


def same_district(sheet_district, google_district):
    """
    True if Google's district name matches the sheet's DISTRICT. Lenient on
    spacing and spelling: "FUTURE CITY-RANGA REDDY" ~ "Rangareddy",
    "KOMARAMBHEEM ASIFABAD" ~ "Kumuram Bheem Asifabad",
    "TIRUCHIRAPPALLI RURAL" ~ "Tiruchirappalli".
    """
    a, b = _norm_state(sheet_district), _norm_state(google_district)
    if not (a and b):
        return False
    if fuzz.token_set_ratio(a, b) >= STATE_MATCH_CUTOFF:
        return True
    a, b = a.replace(" ", ""), b.replace(" ", "")
    shorter, longer = sorted((a, b), key=len)
    return (len(shorter) >= 5 and shorter in longer) or fuzz.ratio(a, b) >= STATE_MATCH_CUTOFF


# ─────────────────────────────────────────────────────────────────────────────
# DISTANCE
# ─────────────────────────────────────────────────────────────────────────────

def geodesic_distance(point1, point2, unit="km"):
    """
    Geodesic (ellipsoidal) distance between two (lat, lng) points.

    Args:
        point1: (latitude, longitude) in decimal degrees
        point2: (latitude, longitude) in decimal degrees
        unit:   "km" | "mi" | "m" | "nmi"

    Returns:
        Distance as float in the requested unit.
    """
    dist = geodesic(point1, point2)

    units = {
        "km":  dist.kilometers,
        "mi":  dist.miles,
        "m":   dist.meters,
        "nmi": dist.nautical,
    }

    if unit not in units:
        raise ValueError(f"Unsupported unit '{unit}'. Choose from {list(units)}.")

    return units[unit]


# ─────────────────────────────────────────────────────────────────────────────
# STATION COORDINATES — STORED IN THE EXCEL ITSELF
# ─────────────────────────────────────────────────────────────────────────────
# Station coordinates are static, so each one is geocoded ONCE and then kept in
# the COL_LAT / COL_LNG columns of the PoliceStation sheet. The Excel is the
# single source of truth — there is no side-car cache file to rebuild or keep
# in sync.
#
# A blank LAT/LNG means the station needs an explicit maintenance run with
# scripts/build_ps_coords.py. Routine lookups do not retry failed stations.
#
# On a normal lookup, every station already has coordinates, so the only live
# API call is the user's input address.

_coords_cache = None
_state_cache  = {}      # (DISTRICT, PS_NAME) -> STATE ("" if blank); filled with _coords_cache
_stateful_coords_cache = {}  # (STATE, DISTRICT, PS_NAME) -> coordinates


def configure_workbook(path):
    """Use the same workbook for matching, coordinates and logging."""
    global EXCEL_FILE, _coords_cache, _state_cache, _stateful_coords_cache
    resolved = Path(path).resolve()
    if resolved != Path(EXCEL_FILE).resolve():
        EXCEL_FILE = resolved
        _coords_cache = None
        _state_cache = {}
        _stateful_coords_cache = {}


def _distinct_name(name):
    return re.sub(r"[^A-Z]", "", str(name).upper())


def coordinate_collisions(coords):
    """Keys at a point also used by a differently named station."""
    by_point = {}
    for key, point in coords.items():
        if point is not None:
            by_point.setdefault(point, []).append(key)
    return {
        key for keys in by_point.values()
        if len({_distinct_name(key[-1]) for key in keys}) > 1
        for key in keys
    }


def _header_index(ws):
    """Map upper-cased header name -> 1-based column index for the first row."""
    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    return {
        str(name).strip().upper(): i
        for i, name in enumerate(header, start=1)
        if name is not None
    }


def _load_coords_cache():
    """
    Lazy-load station coordinates from the PoliceStation sheet into a dict:
        (DISTRICT, PS_NAME) -> (lat, lng)   both values present and numeric
        (DISTRICT, PS_NAME) -> None         blank or unparseable — needs geocoding

    Each row's STATE is read in the same pass into _state_cache, so a station's
    geocode query is always built from its own row.

    An unreadable workbook yields an empty dict (with a warning) rather than
    raising, so a lookup degrades to "no distance ranking" instead of crashing.
    """
    global _coords_cache, _stateful_coords_cache
    if _coords_cache is None:
        _coords_cache = {}
        try:
            # Default data_only=False: this workbook holds formulas on other
            # sheets, and we must never round-trip them into static values.
            ws = openpyxl.load_workbook(EXCEL_FILE)[SHEET_NAME]
        except Exception as e:
            print(f"  [WARN] Could not read station coordinates from {EXCEL_FILE}: {e}")
            return _coords_cache

        cols    = _header_index(ws)
        i_dist  = cols.get(COL_DISTRICT.upper())
        i_ps    = cols.get(COL_PS.upper())
        i_lat   = cols.get(COL_LAT.upper())
        i_lng   = cols.get(COL_LNG.upper())
        i_state = cols.get(COL_STATE.upper())

        if not i_dist or not i_ps:
            print(f"  [WARN] '{SHEET_NAME}' is missing the "
                  f"{COL_DISTRICT}/{COL_PS} columns — no coordinates loaded.")
            return _coords_cache

        for row in ws.iter_rows(min_row=2, values_only=True):
            district, ps = row[i_dist - 1], row[i_ps - 1]
            if district is None or ps is None:
                continue

            key = (str(district).strip().upper(), str(ps).strip().upper())

            # LAT/LNG columns may not exist yet on a first run — that is simply
            # "nothing geocoded so far", not an error.
            lat = row[i_lat - 1] if i_lat and i_lat <= len(row) else None
            lng = row[i_lng - 1] if i_lng and i_lng <= len(row) else None

            # No STATE column, or a blank cell, is recorded as "" — never
            # defaulted. station_geocode_query() refuses to build a query for it.
            state = row[i_state - 1] if i_state and i_state <= len(row) else None
            state_text = "" if state is None else str(state).strip().upper()
            _state_cache[key] = state_text

            try:
                point = (float(lat), float(lng))
                _coords_cache[key] = point
                _stateful_coords_cache[(state_text, *key)] = point
            except (TypeError, ValueError):
                _coords_cache[key] = None      # blank or junk → needs geocoding
                _stateful_coords_cache[(state_text, *key)] = None

    return _coords_cache


# A leading station code, as Chennai / Tambaram / Madurai city stations carry:
# "K-4 ANNANAGAR", "T16 SAMMANCHERI", "D3-KOODAL PUDUR", "E5 MATTUTHAVANI".
# One or two letters, optional hyphen, digits, then a space or hyphen. Names
# without digits ("T NARASAPURAM", "II TOWN") are untouched.
_STATION_CODE = re.compile(r"^[A-Z]{1,2}\s*-?\s*\d{1,3}[A-Z]?\s*[-\s]\s*")


def clean_station_name(ps):
    """
    The station name as a geocoder can search it. The sheet is never changed —
    this only shapes the query text.

        "K-4 ANNANAGAR"     -> "ANNANAGAR"
        "E3-ANNA .NAGAR."   -> "ANNA NAGAR"
        "BHAVANI P.S"       -> "BHAVANI"
        "PRODDATUR U/G"     -> "PRODDATUR U G"
        "P.N.PALAYAM"       -> "P.N.PALAYAM"   (initials kept)

    Falls back to the raw name if cleaning would leave nothing.
    """
    raw  = str(ps).strip().upper()
    name = _STATION_CODE.sub("", raw)
    name = strip_ps_noise(name)
    name = re.sub(r"(?:(?<=\s)|^)\.+|\.+$", " ", name)   # stray dots, not initials
    name = re.sub(r"[/()\[\]]", " ", name)
    name = " ".join(name.split())
    return name or raw


_search_names = None


def search_name(district, ps):
    """
    The name to search Google with: the station's entry in SEARCH_ALIAS_FILE
    if it has one, else its sheet name. Search text only — the sheet is never
    changed, and every check still applies to what Google returns.
    """
    global _search_names
    if _search_names is None:
        import csv
        _search_names = {}
        if SEARCH_ALIAS_FILE.exists():
            with open(SEARCH_ALIAS_FILE, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    d, p, s = (str(row.get(k) or "").strip().upper()
                               for k in (COL_DISTRICT, COL_PS, "SEARCH NAME"))
                    if d and p and s:
                        _search_names[(d, p)] = s
    key = (str(district).strip().upper(), str(ps).strip().upper())
    return _search_names.get(key, ps)


def station_geocode_query(ps, district, state):
    """
    The geocode query for one station, built from that station's own row:
        "{clean PS_NAME} Police Station, {DISTRICT}, {STATE}, India"
    with PS_NAME replaced by its search name, if SEARCH_ALIAS_FILE has one.

    Returns None when STATE is blank. There is no fallback state: district names
    repeat across states, so a guessed state yields a confident wrong location,
    and a wrong coordinate once written is never retried.
    """
    state = "" if state is None else str(state).strip()
    if not state:
        return None
    name = clean_station_name(search_name(district, ps))
    return f"{name} Police Station, {district}, {state}, India"


def coords_in_envelope(lat, lng):
    """True if (lat, lng) lies inside India's outer bounding box (COORD_*)."""
    return (COORD_LAT_MIN <= lat <= COORD_LAT_MAX
            and COORD_LNG_MIN <= lng <= COORD_LNG_MAX)


def geocode_station(district, ps):
    """
    Geocode one station, or return None and say why. Returns (lat, lng) only
    for a result that is safe to write. Three ways to get None, each named:

      - the row has no STATE        → skipped, no API call
      - the geocoder returned nothing
      - Google places the result in a different state than the row's STATE,
        outside India's outer box (COORD_*), or only at a state / district /
        taluk centre (station itself not found), or more than SIBLING_MAX_KM
        from every other station in its district (same-name village) → rejected

    In every None case the cell stays blank and is retried next run.
    """
    _load_coords_cache()
    key   = (str(district).strip().upper(), str(ps).strip().upper())
    query = station_geocode_query(ps, district, _state_cache.get(key, ""))

    if query is None:
        print(f"  [WARN] Skipped {ps} ({district}): STATE is blank in "
              f"'{SHEET_NAME}' — not geocoded, left blank.")
        return None

    top = _geocode_top(query)                    # returns None on any failure
    if not top:
        print(f"  [WARN] Could not geocode station: {query}")
        return None

    (lat, lng), formatted = _coords_and_formatted(top)
    if not coords_in_envelope(lat, lng):
        print(f"  [WARN] Rejected {ps} ({district}): ({lat}, {lng}) "
              f"'{formatted}' is outside India — left blank.")
        return None

    vague = vague_result_type(top)
    if vague:
        print(f"  [WARN] Rejected {ps} ({district}): Google did not find the "
              f"station, only the area centre ({vague}: '{formatted}') — left "
              f"blank. Check the station name in the Excel.")
        return None

    sheet_state, google_state = _state_cache.get(key, ""), result_state(top)
    if google_state and not google_state.isascii():
        google_state = _english_state_at(lat, lng) or google_state
    if not same_state(sheet_state, google_state):
        print(f"  [WARN] Rejected {ps} ({district}): Google placed it in "
              f"'{google_state or 'no state'}', sheet says '{sheet_state}' "
              f"('{formatted}') — left blank. If both name the same state, "
              f"fix the spelling in the STATE column.")
        return None

    km = isolated_from_siblings(key, lat, lng, _load_coords_cache())
    google_district = result_district(top)
    if km and not same_district(district, google_district):
        print(f"  [WARN] Rejected {ps} ({district}): Google placed it in "
              f"'{google_district or 'unknown district'}' ('{formatted}'), "
              f"{km:.0f} km from every other station in {district} — likely a "
              f"same-name place elsewhere, left blank. Check the station name "
              f"in the Excel.")
        return None

    return lat, lng


# ── Re-placing stacked stations ───────────────────────────────────────────────
# For a small station Google's "X Police Station" search often falls back to a
# bigger police building nearby, so many stations end up on one point (e.g. 18
# Madurai Rural stations on one coordinate). Such a station usually sits in the
# village or town it is named after, so that place's point is a far better
# location. Measured trial: 11 of 20 stacked stations moved 2–60 km to their own
# village; the rest kept their point for a stated reason.

# Result / component types that mean "a named village, town or neighbourhood".
PLACE_TYPES = {
    "locality", "sublocality", "sublocality_level_1", "sublocality_level_2",
    "neighborhood", "administrative_area_level_4", "postal_town",
}

# Words that qualify a station but are not part of the place it is named after:
# "ADILABAD II TOWN", "NANDYAL TALUKA", "BODI TRAFFIC", "MYDUKUR U G".
_PLACE_QUALIFIERS = re.compile(
    r"\b(?:I{1,3}|IV|\d)?\s*(?:TOWN|RURAL|TALUK|TALUKA|URBAN|NORTH|SOUTH|EAST|WEST|"
    r"NEW|OLD|TRAFFIC|AWPS|U G|L AND O)\b")


def station_place_name(ps):
    """The village / town a station is named after: "ADILABAD II TOWN" -> "ADILABAD"."""
    name  = clean_station_name(ps)
    place = " ".join(_PLACE_QUALIFIERS.sub(" ", name).split())
    return place or name


def geocode_station_place(district, ps, coords):
    """
    ((lat, lng), detail) for the village / town station `ps` is named after, or
    (None, reason). Accepted only if the result IS a village / town /
    neighbourhood whose name matches the station's place name, lies in the
    row's STATE, is not isolated from its district, and differs from the
    stored point. One Geocoding call; nothing is written here.
    """
    key   = (str(district).strip().upper(), str(ps).strip().upper())
    state = _state_cache.get(key, "")
    if not state:
        return None, "STATE is blank"
    place = station_place_name(search_name(district, ps))
    top   = _geocode_top(f"{place}, {district}, {state}, India")
    if not top:
        return None, "no result"

    (lat, lng), _ = _coords_and_formatted(top)
    if not set(top.get("types", [])) & PLACE_TYPES:
        return None, "Google found no village or town of that name"
    names = [c["long_name"] for c in top.get("address_components", [])
             if set(c.get("types", [])) & PLACE_TYPES]
    target = _distinct_name(place)

    def _same_place(found):
        # Similar spelling AND similar length: "T.V.NALLUR" (Thiruvennainallur)
        # must not be answered by any village called plain "Nallur".
        found = _distinct_name(found)
        short, long_ = sorted((len(target), len(found)))
        return (fuzz.ratio(target, found) >= STATION_PLACE_MATCH
                and long_ and short / long_ >= 0.8)

    if not any(_same_place(n) for n in names):
        return None, f"place name does not match ({', '.join(names[:2]) or 'none'})"
    if not coords_in_envelope(lat, lng) or not same_state(state, result_state(top)):
        return None, "outside the row's state"
    if isolated_from_siblings(key, lat, lng, coords):
        return None, "far from every other station in its district"
    old = coords.get(key)
    if old and geodesic_distance((lat, lng), old) < 0.2:
        return None, "already at its own town"
    moved = geodesic_distance((lat, lng), old) if old else 0
    return (lat, lng), f"{names[0]}, moved {moved:.1f} km"


# ── Sibling check ─────────────────────────────────────────────────────────────
# Village names repeat inside a state (KEERANUR is in Dindigul AND Pudukkottai;
# BALANAGAR in Mahabubnagar AND Hyderabad), so a result can pass the state
# check and still be 100+ km off. Rejected only when BOTH signals agree:
#
#   1. Isolated: more than SIBLING_MAX_KM from every other station of its own
#      district in the sheet. Across ~3,000 stations, 99% are within ~21 km of
#      a sibling; the wrong results were 41–251 km out.
#   2. Google names a different district for it than the row's DISTRICT.
#
# Either alone gives false alarms: remote-but-real stations (EAGALAPENTA by
# the Srisailam dam) are isolated, and redrawn boundaries (Bapatla from
# Prakasam) or commissionerates (AVADI, CYBERABAD) differ in name only.
# The isolation test is skipped while a district has fewer than
# SIBLING_MIN_COUNT stored stations — the bulk fill re-checks the whole batch.


def isolated_from_siblings(key, lat, lng, coords):
    """
    km to the nearest other station of the same district if that is more than
    SIBLING_MAX_KM, else 0. `coords` maps (DISTRICT, PS) -> (lat, lng) or None.
    Returns 0 (cannot judge) when the district has too few stored siblings.
    """
    district = key[0]
    siblings = [c for k, c in coords.items()
                if k[0] == district and k != key and c is not None]
    if len(siblings) < SIBLING_MIN_COUNT:
        return 0
    nearest = min(geodesic((lat, lng), c).km for c in siblings)
    return nearest if nearest > SIBLING_MAX_KM else 0


def audit_station(district, ps, lat, lng, coords=None):
    """
    Re-check a stored coordinate against the sibling rule. "" if it holds,
    else the reason. Free for a station near its siblings; an isolated one is
    re-geocoded once to ask Google which district it is in.
    """
    coords = _load_coords_cache() if coords is None else coords
    key = (str(district).strip().upper(), str(ps).strip().upper())
    km  = isolated_from_siblings(key, lat, lng, coords)
    if not km:
        return ""
    top = _geocode_top(station_geocode_query(ps, district, _state_cache.get(key, "")))
    google_district = result_district(top) if top else ""
    if same_district(district, google_district):
        return ""
    return (f"Google says '{google_district or 'unknown district'}', "
            f"{km:.0f} km from every other station in {district}")


def _clear_coords(keys):
    """Blank LAT/LNG for the given (district, ps) keys, in one save."""
    try:
        wb   = openpyxl.load_workbook(EXCEL_FILE)
        ws   = wb[SHEET_NAME]
        cols = _header_index(ws)
        i_dist, i_ps = cols.get(COL_DISTRICT.upper()), cols.get(COL_PS.upper())
        i_lat,  i_lng = cols.get(COL_LAT.upper()), cols.get(COL_LNG.upper())
        wanted  = set(keys)
        cleared = 0
        for r in range(2, ws.max_row + 1):
            k = (str(ws.cell(row=r, column=i_dist).value).strip().upper(),
                 str(ws.cell(row=r, column=i_ps).value).strip().upper())
            if k in wanted:
                # .value = None, not cell(value=None): openpyxl ignores a None
                # passed to cell() and would leave the old coordinate in place.
                ws.cell(row=r, column=i_lat).value = None
                ws.cell(row=r, column=i_lng).value = None
                cleared += 1
        if cleared:
            wb.save(EXCEL_FILE)
        print(f"  [SAVED] {cleared} wrong coordinate(s) cleared in '{SHEET_NAME}'.")
    except Exception as e:
        print(f"  [WARN] Could not clear coordinates in {EXCEL_FILE.name}: {e}")


def _write_coords(updates):
    """
    Write freshly geocoded coordinates back into the PoliceStation sheet, in a
    single save. `updates` is a list of (district, ps_name, lat, lng).

    The LAT/LNG columns are created on first use. Written with openpyxl so the
    workbook's other sheets — including their formulas and tables — survive
    untouched, the same way lookup_log.py appends to LookupLogs.

    A failed save (most often: the file is open in Excel) is reported and
    swallowed. The coordinates still apply to the current lookup from memory;
    they are simply re-geocoded next time instead of costing a crash.
    """
    proposed = dict(_load_coords_cache())
    proposed.update({(str(d).strip().upper(), str(p).strip().upper()): (la, ln)
                     for d, p, la, ln in updates})
    collisions = coordinate_collisions(proposed)
    safe_updates = []
    for district, ps, lat, lng in updates:
        if (str(district).strip().upper(), str(ps).strip().upper()) in collisions:
            print(f"  [WARN] Not writing {ps} ({district}): differently named "
                  "station shares that coordinate; review required.")
        else:
            safe_updates.append((district, ps, lat, lng))
    if not safe_updates:
        return
    try:
        wb = openpyxl.load_workbook(EXCEL_FILE)
        ws = wb[SHEET_NAME]

        cols   = _header_index(ws)
        i_dist = cols.get(COL_DISTRICT.upper())
        i_ps   = cols.get(COL_PS.upper())
        i_lat  = cols.get(COL_LAT.upper())
        i_lng  = cols.get(COL_LNG.upper())

        # Create the coordinate columns the first time we ever write.
        if not i_lat:
            i_lat = ws.max_column + 1
            ws.cell(row=1, column=i_lat, value=COL_LAT)
        if not i_lng:
            i_lng = ws.max_column + 1
            ws.cell(row=1, column=i_lng, value=COL_LNG)

        # (district, ps) -> sheet row number
        row_of = {}
        for r in range(2, ws.max_row + 1):
            district = ws.cell(row=r, column=i_dist).value
            ps       = ws.cell(row=r, column=i_ps).value
            if district is None or ps is None:
                continue
            row_of.setdefault(
                (str(district).strip().upper(), str(ps).strip().upper()), r
            )

        written = 0
        for district, ps, lat, lng in safe_updates:
            # Last line of defence: never persist an out-of-envelope coordinate,
            # whoever the caller is.
            if not coords_in_envelope(lat, lng):
                print(f"  [WARN] Not writing {ps} ({district}): ({lat}, {lng}) is "
                      f"outside India — left blank.")
                continue
            r = row_of.get((str(district).strip().upper(), str(ps).strip().upper()))
            if r is None:
                continue
            ws.cell(row=r, column=i_lat, value=lat)
            ws.cell(row=r, column=i_lng, value=lng)
            written += 1

        if not written:
            return                      # nothing survived the guard — don't touch the file

        wb.save(EXCEL_FILE)
        print(f"  [SAVED] {written} station coordinate(s) written to "
              f"'{SHEET_NAME}' in {EXCEL_FILE.name}")

    except Exception as e:
        print(f"  [WARN] Could not save coordinates to {EXCEL_FILE.name}: {e}")
        print(f"         (Is the file open in Excel? Results are still correct; "
              f"these stations will be geocoded again next time.)")


class MeasuredResults(list):
    """Distances with the state reported by the validated address geocode."""

    def __init__(self, iterable=(), address_state=""):
        super().__init__(iterable)
        self.address_state = address_state


def measure_from_address(input_address, stations, expected_state=None):
    """
    Geocode the input address once and measure the geodesic distance to each
    station in `stations`, a list of (state, district, ps_name) for the active
    nearest-three path, or (district, ps_name) for legacy callers.

    Returns None if the address itself cannot be geocoded. Otherwise a list, in
    the input order, of dicts:
        { police_station, district, distance_km }   distance_km None → no coords

    Used where the answer is already narrowed by text or state and distance is
    a check or a ranking over known rows — so, unlike rank_ps_by_distance(),
    missing station coordinates are NOT geocoded here: a nationwide call would
    otherwise fan out into hundreds of API calls. A station without coordinates
    is reported with distance_km None and never guessed at. Run
    scripts/build_ps_coords.py to fill them.
    """
    cache  = _load_coords_cache()
    stateful = bool(stations and len(stations[0]) == 3)
    source = _stateful_coords_cache if stateful else cache
    collisions = coordinate_collisions(source)
    origin = geocode_address(input_address, expected_state=expected_state,
                             return_state=True)
    if not origin:
        print(f"  [WARN] Could not geocode input address: '{input_address}'")
        return None

    origin_coords = origin[0]
    address_state = origin[2] if len(origin) > 2 else ""
    out = []
    for station in stations:
        if stateful:
            state, district, ps = station
            key = (str(state).strip().upper(), str(district).strip().upper(),
                   str(ps).strip().upper())
        else:
            district, ps = station
            state = ""
            key = (str(district).strip().upper(), str(ps).strip().upper())
        coords = source.get(key)
        out.append({
            "police_station": ps,
            "district":       district,
            "state":          state,
            "distance_km":    geodesic_distance(origin_coords, coords) if coords else None,
            "station_coordinates": coords,
            "coordinate_unverified": key in collisions,
        })
    return MeasuredResults(out, address_state=address_state)


class RankedResults(list):
    """
    A plain list of ranked result dicts, plus `excluded`: the station names
    that could not be distance-ranked because they have no coordinates and
    could not be geocoded. Callers read it defensively via
    getattr(ranked, "excluded", []), so anything that substitutes a plain
    list (e.g. the test harness mock) still works unchanged.
    """
    def __init__(self, iterable=(), excluded=None):
        super().__init__(iterable)
        self.excluded = list(excluded or [])


# ─────────────────────────────────────────────────────────────────────────────
# PS RANKING BY REAL DISTANCE
# ─────────────────────────────────────────────────────────────────────────────

def rank_ps_by_distance(input_address, ps_list, district, top_n=TOP_N):
    """
    Geocode the input address, read each Police Station's coordinates from the
    PoliceStation sheet, compute real geodesic distance, and return top_n
    sorted closest first.

    The input address is the only geocode call. Missing station coordinates
    are excluded and reported for explicit maintenance.

    This replaces the AI distance-estimation that was in ai_engine.py.
    Distance is now a real number from real coordinates, not a guess.

    Args:
        input_address : raw address string from the user
        ps_list       : list of Police Station names (strings) for this district
        district      : district name — cache lookup key alongside each PS name
        top_n         : number of results to return (default: config.TOP_N)

    Returns:
        RankedResults (a list) of dicts:
            { police_station, district, distance, distance_km, resolved_address }
        `distance` is the display string ("~12.3 km"); `distance_km` is the
        unrounded float, kept for sorting and for callers that need to compare
        against a threshold (see engine.py's Case 2 sanity check).
        `.excluded` lists stations skipped because they have no coordinates and
        could not be geocoded — excluded, noted, never guessed.
        Empty if the input address couldn't be geocoded.

    Note on jurisdiction vs distance:
        Nearest by straight-line distance is NOT the same as correct jurisdiction.
        Jurisdiction boundaries are administrative — this ranking is a strong
        signal, not a guaranteed answer. Always return top_n, not just 1.
    """
    cache        = _load_coords_cache()
    district_key = str(district).strip().upper()

    # Missing coordinates require explicit enrichment. Do not retry failed
    # station geocodes during every ordinary lookup.
    missing = [
        ps for ps in ps_list
        if cache.get((district_key, str(ps).strip().upper())) is None
    ]
    if missing:
        print(f"  [WARN] {len(missing)} station(s) lack coordinates; run "
              "scripts/build_ps_coords.py for explicit enrichment.")
    collisions = coordinate_collisions(cache)

    # Anything still without coordinates could not be geocoded at all. It is
    # excluded from the ranking and reported by name — never guessed at.
    excluded = [
        ps for ps in ps_list
        if cache.get((district_key, str(ps).strip().upper())) is None
    ]
    if excluded:
        print(f"  [WARN] {len(excluded)} station(s) in {district} could not be "
              f"geocoded — excluded from distance ranking.")

    origin_result = geocode_address(input_address)     # the 1 live API call

    if not origin_result:
        print(f"  [WARN] Could not geocode input address: '{input_address}'")
        return RankedResults([], excluded=excluded)

    origin_coords, _ = origin_result
    results = []

    for ps in ps_list:
        coords = cache.get((district_key, str(ps).strip().upper()))
        if coords is None:
            continue                                   # already in `excluded`

        dist_km = geodesic_distance(origin_coords, coords, unit="km")

        results.append({
            "police_station":   ps,
            "district":         district,
            "distance":         f"~{round(dist_km, 1)} km",
            "distance_km":      dist_km,      # unrounded — for sorting and callers
            "coordinate_unverified": (district_key, str(ps).strip().upper()) in collisions,
            "resolved_address": "",           # coords come from the sheet, not a live geocode
        })

    # Sort by real distance, take top N
    results.sort(key=lambda x: (x["distance_km"], x["police_station"]))

    return RankedResults(results[:top_n], excluded=excluded)


def rank_ps_nearby_any_district(input_address, df, top_n=TOP_N):
    """
    Rank stations across EVERY district present in `df`, closest first.

    Same cache and same arithmetic as rank_ps_by_distance. The only difference
    is that the cache key's district comes from each row rather than one fixed
    district, so a station sitting just the other side of a district boundary
    is visible instead of being filtered out before distance is ever computed.

    Why this costs nothing extra: station coordinates are read from the prebuilt
    cache, and the one geocode of `input_address` is memoised on _geocode_top.
    Scanning every district is therefore arithmetic over rows already in memory
    — no additional API call, whatever the district count.

    Args:
        input_address : raw address string from the user
        df            : DataFrame already narrowed to the search scope (state)
        top_n         : number of results to return

    Returns:
        RankedResults of the same dicts rank_ps_by_distance produces, each
        carrying its own `district`. Empty if the address could not be geocoded.
    """
    cache = _load_coords_cache()

    origin_result = geocode_address(input_address)
    if not origin_result:
        return RankedResults([], excluded=[])
    origin_coords, _ = origin_result

    collisions = coordinate_collisions(cache)
    results, excluded = [], []

    # Deduplicate: the sheet can repeat a (district, station) pair across rows.
    seen = set()
    for district, ps in zip(df[COL_DISTRICT], df[COL_PS]):
        key = (str(district).strip().upper(), str(ps).strip().upper())
        if key in seen:
            continue
        seen.add(key)

        coords = cache.get(key)
        if coords is None:
            excluded.append(f"{ps} ({district})")
            continue

        dist_km = geodesic_distance(origin_coords, coords, unit="km")
        results.append({
            "police_station":   ps,
            "district":         district,
            "distance":         f"~{round(dist_km, 1)} km",
            "distance_km":      dist_km,
            "coordinate_unverified": key in collisions,
            "resolved_address": "",
        })

    results.sort(key=lambda x: (x["distance_km"], x["police_station"]))
    return RankedResults(results[:top_n], excluded=excluded)
