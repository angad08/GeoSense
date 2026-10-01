"""
GeoSense — common/state_filter.py  (shared)
--------------------------------------------
Narrows the station list to the state the address names, BEFORE any case of
the ladder runs. Shared by v1 and v2 — behaviour is identical in both.

Station names repeat across states (NAWABPET, ATMAKUR, ...) but a person lives
in exactly one state, so a Telangana address must never be offered an Andhra
Pradesh station, and vice versa.

The recognised states are read from the STATE column of the Excel — nothing is
hardcoded. Adding a state to the master list needs no code change here.

Rules:
  - Exactly one state named in the address → search only that state's stations.
  - No state named, or more than one      → search every state, and say so.
Only full state names count (small spelling slips like TELENGANA are tolerated
via STATE_MATCH_CUTOFF). Abbreviations such as AP / TS are deliberately NOT
recognised: they occur inside ordinary address text, and a wrong narrowing
would hide the correct station entirely.
"""

import re

from rapidfuzz import fuzz

from common.config import COL_STATE, STATE_MATCH_CUTOFF


def _words(text):
    """Upper-case the text and split on anything that is not a letter/digit."""
    return re.sub(r"[^A-Z0-9]+", " ", str(text).upper()).split()


def states_in_sheet(df):
    """Distinct non-blank STATE values present in the DataFrame, sorted."""
    if COL_STATE not in df.columns:
        return []
    return sorted({s for s in df[COL_STATE] if isinstance(s, str) and s.strip()})


def region_phrase(df):
    """
    The states being searched, as prompt text: "Tamil Nadu" or
    "Andhra Pradesh, Tamil Nadu and Telangana". "India" if the sheet has no
    STATE values. Read from the (possibly state-narrowed) DataFrame, so the
    AI is told exactly the region its district list covers.
    """
    names = [s.strip().title() for s in states_in_sheet(df)]
    if not names:
        return "India"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def district_list_text(df, col_district):
    """
    Bullet list of districts for a prompt. With several states the list is
    grouped under state headings, since district names can repeat across
    states and the grouping gives the AI the geography it reasons over.
    """
    states = states_in_sheet(df)
    if len(states) <= 1:
        return "\n".join(f"- {d}" for d in sorted(df[col_district].unique()))
    blocks = []
    for state in states:
        districts = sorted(df[df[COL_STATE] == state][col_district].unique())
        blocks.append(f"{state}:\n" + "\n".join(f"- {d}" for d in districts))
    return "\n\n".join(blocks)


def detect_states(address, df):
    """
    Every state from the sheet that the address names, as a sorted list.

    A state of n words is compared against each run of 1..n consecutive address
    words, with spaces removed on both sides, so "ANDHRA PRADESH",
    "ANDHRAPRADESH" and "ANDHRA-PRADESH" all match, and a one-letter slip still
    clears STATE_MATCH_CUTOFF. A lone "ANDHRA" does not.
    """
    words = _words(address)
    found = set()
    for state in states_in_sheet(df):
        target = state.replace(" ", "")
        n      = len(state.split())
        for size in range(1, n + 1):
            for i in range(len(words) - size + 1):
                window = "".join(words[i:i + size])
                if fuzz.ratio(window, target) >= STATE_MATCH_CUTOFF:
                    found.add(state)
                    break
            if state in found:
                break
    return sorted(found)


def filter_by_state(address, df):
    """
    Returns (df_to_search, state_scope, state).

    df_to_search : only the named state's rows when exactly one state is named;
                   otherwise the full DataFrame, unchanged.
    state_scope  : one plain-English line saying which stations were searched
                   and why — attached to every result so it is always visible.
    state        : the single state named, or None (none named, or several).
    """
    named = detect_states(address, df) if str(address).strip() else []

    if len(named) == 1:
        state = named[0]
        return (df[df[COL_STATE] == state].reset_index(drop=True),
                f"State: {state} (named in address) — only {state} stations searched",
                state)

    if len(named) > 1:
        return (df, f"State: address names more than one state ({', '.join(named)}) "
                    f"— all states searched", None)

    return (df, "State: not named in address — all states searched", None)
