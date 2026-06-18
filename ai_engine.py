"""
GeoSense — ai_engine.py
------------------------
AI client initialisation, call wrapper, and all AI reasoning functions.
Supports Anthropic, OpenAI, and Gemini through a unified interface.

The AI is used for reasoning only — it cannot invent Police Station or
District names. All final answers are validated against the Excel.
"""

import os
import re
import sys
import json

from config import AI_PROVIDER, AI_MODEL, TOP_N, COL_DISTRICT, COL_PS
from matcher import find_district_in_excel


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT SETUP
# ─────────────────────────────────────────────────────────────────────────────

def initiateAgent():
    """
    Return the appropriate client object for the configured AI_PROVIDER.
    Reads the API key from environment variables.
    Exits with a clear error message if the key is missing or the package
    is not installed.
    """
    if AI_PROVIDER == "anthropic":
        try:
            import anthropic
        except ImportError:
            print("[ERROR] anthropic package not installed.")
            print("        Run: pip install anthropic")
            sys.exit(1)
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            print("[ERROR] ANTHROPIC_API_KEY not set.")
            print("        Run: export ANTHROPIC_API_KEY=sk-ant-...")
            sys.exit(1)
        return anthropic.Anthropic(api_key=key)

    elif AI_PROVIDER == "openai":
        try:
            from openai import OpenAI
        except ImportError:
            print("[ERROR] openai package not installed.")
            print("        Run: pip install openai")
            sys.exit(1)
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            print("[ERROR] OPENAI_API_KEY not set.")
            print("        Run: export OPENAI_API_KEY=sk-...")
            sys.exit(1)
        return OpenAI(api_key=key)

    elif AI_PROVIDER == "gemini":
        try:
            import google.generativeai as genai
        except ImportError:
            print("[ERROR] google-generativeai package not installed.")
            print("        Run: pip install google-generativeai")
            sys.exit(1)
        key = os.environ.get("GOOGLE_API_KEY", "")
        if not key:
            print("[ERROR] GOOGLE_API_KEY not set.")
            print("        Run: export GOOGLE_API_KEY=AI...")
            sys.exit(1)
        genai.configure(api_key=key)
        return genai.GenerativeModel(AI_MODEL)

    else:
        print(f"[ERROR] Unknown AI_PROVIDER: '{AI_PROVIDER}'")
        print("        Choose from: 'anthropic', 'openai', 'gemini'")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# LAZY CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class LazyAgent:
    """
    Defers AI client creation until an AI call is actually needed.

    Fuzzy-only lookups (Case 1 — known PS, and Case 3a — address names a PS)
    never touch the AI, so they must run with NO API key and NO cost. By passing
    a LazyAgent around instead of a live client, initiateAgent() — which exits
    when the key is missing — is only invoked the moment an AI path is reached
    (Case 2/3b ranking with many candidates, or Case 3c reasoning).
    """
    def __init__(self):
        self._client = None

    def resolve(self):
        if self._client is None:
            self._client = initiateAgent()
        return self._client


# ─────────────────────────────────────────────────────────────────────────────
# CALL WRAPPER
# ─────────────────────────────────────────────────────────────────────────────

def invokeAgent(prompt, client):
    """
    Send a prompt to the AI and return the response text.
    Unified interface for Anthropic, OpenAI, and Gemini.
    Raises an exception on failure — callers handle it.

    Accepts either a live client or a LazyAgent (resolved on first use here).
    """
    if isinstance(client, LazyAgent):
        client = client.resolve()

    if AI_PROVIDER == "anthropic":
        resp = client.messages.create(
            model=AI_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    elif AI_PROVIDER == "openai":
        resp = client.chat.completions.create(
            model=AI_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()

    elif AI_PROVIDER == "gemini":
        resp = client.generate_content(prompt)
        return resp.text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# AI REASONING FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def rankingAgent(address, district, ps_candidates, client):
    """
    Case 2 helper — District is known, address is available.

    Asks the AI to rank which Police Stations from ps_candidates best match
    the address, and estimate approximate straight-line distance in km.

    The AI can only pick from ps_candidates — it cannot invent new names.
    Returns a list of dicts: { police_station, distance }
    """
    if len(ps_candidates) <= TOP_N:
        return [{"police_station": ps, "distance": "N/A"} for ps in ps_candidates]

    candidate_text = "\n".join(f"- {ps}" for ps in ps_candidates)

    prompt = f"""You are helping identify the correct Police Station for passport enrollment verification.

IMPORTANT:
- The district has already been identified.
- You MUST choose ONLY from the supplied police station list.
- Never invent a Police Station.
- Never return a Police Station that is not present in the list.
- Use locality names, landmarks, villages, mandals, suburbs and PIN codes from the address.
- Think like a Hyderabad/Telangana passport verification officer.
- Also estimate the approximate straight-line distance in km from the address to each police station area.

ADDRESS:
{address.strip()}

DISTRICT:
{district}

AVAILABLE POLICE STATIONS:
{candidate_text}

TASK:
Rank the best {TOP_N} police stations and estimate distance from the address.

Return ONLY a JSON array (no explanation):
[
  {{"name": "POLICE_STATION_1", "dist_km": 5}},
  {{"name": "POLICE_STATION_2", "dist_km": 12}},
  {{"name": "POLICE_STATION_3", "dist_km": 18}}
]"""

    try:
        raw   = invokeAgent(prompt, client)
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            items   = json.loads(match.group())
            results = []
            for item in items:
                name = str(item.get("name", "")).strip().upper()
                dist = item.get("dist_km")
                if name in ps_candidates:
                    results.append({
                        "police_station": name,
                        "distance": f"~{round(dist)} km" if isinstance(dist, (int, float)) else "N/A",
                    })
            if results:
                return results[:TOP_N]

    except Exception as e:
        print(f"  [WARN] AI ranking failed: {e}. Using first {TOP_N} from list.")

    return [{"police_station": ps, "distance": "N/A"} for ps in ps_candidates[:TOP_N]]


def inferDistrict(address, df, client):
    """
    Case 3 — Neither PS nor District is known. Only address is available.

    Step 1: AI infers which district the address belongs to (from the Excel
            district list — no invented names).
    Step 2: AI ranks the best Police Stations within that district.

    No internet. Pure geographic reasoning.
    All final answers are validated against the Excel.
    Returns a list of dicts: { police_station, district, confidence }
    """
    all_districts = sorted(df[COL_DISTRICT].unique().tolist())
    district_text = "\n".join(f"- {d}" for d in all_districts)

    # ── Step 1: Infer district ────────────────────────────────────────────────
    prompt_step1 = f"""You are helping identify the correct Police Station for passport enrollment verification in Hyderabad and Telangana.

You will be given:
1. An address.
2. A list of valid districts from an Excel file.

IMPORTANT RULES:
- The address may contain locality names, landmarks, villages, mandals, suburbs, area names and PIN codes.
- Use your knowledge of Hyderabad, Cyberabad and Telangana geography.
- Carefully analyse locality names before deciding the district.
- Locality names are often stronger indicators than district names.
- Do NOT invent districts.
- You MUST choose only from the supplied district list.

ADDRESS:
{address.strip()}

AVAILABLE DISTRICTS:
{district_text}

TASK:
1. Identify important locality names present in the address.
2. Infer the most likely district.
3. If genuinely uncertain, provide up to 2 districts.
4. Think like a passport verification officer familiar with Hyderabad and Telangana locations.

Return ONLY JSON:
{{"districts": ["DISTRICT_NAME"]}}
or
{{"districts": ["DISTRICT_1", "DISTRICT_2"]}}"""

    inferred_districts = []

    try:
        raw   = invokeAgent(prompt_step1, client)
        match = re.search(r'\{.*\}', raw, re.DOTALL)

        if match:
            data         = json.loads(match.group())
            raw_districts = [str(d).strip().upper() for d in data.get("districts", [])]

            for d in raw_districts:
                if d in all_districts:
                    inferred_districts.append(d)            # exact match
                else:
                    hits = find_district_in_excel(d, df)    # fuzzy fallback
                    if hits:
                        inferred_districts.append(hits[0]["district"])

            # Remove duplicates, preserve order
            inferred_districts = list(dict.fromkeys(inferred_districts))

    except Exception as e:
        print(f"  [WARN] AI district step failed: {e}")
        return []

    if not inferred_districts:
        print("  [WARN] AI could not determine a district from the address.")
        return []

    # ── Step 2: Rank PS within each inferred district ─────────────────────────
    all_results = []

    for district in inferred_districts[:2]:           # at most 2 districts
        ps_in_district = df[df[COL_DISTRICT] == district][COL_PS].tolist()
        ranked         = rankingAgent(address, district, ps_in_district, client)

        for i, item in enumerate(ranked[:2]):         # top 2 per district
            all_results.append({
                "police_station": item["police_station"],
                "district":       district,
                "confidence":     "MEDIUM" if i == 0 else "LOW",
                "distance":       item.get("distance", "N/A"),
            })

    return all_results[:TOP_N]
