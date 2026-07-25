"""
GeoSense — v2/ai_engine.py
---------------------------
V2's single AI job:
  Case 3, Step 1 — infer which district a messy address belongs to,
  by reasoning over Telangana geography from the address text.

The client plumbing (init_ai_client, LazyAgent, call_ai) is shared and lives
in common/ai_client.py. Everything that was previously AI-estimated (distance,
PS ranking) is handled by real geocoding in geopy_distance.py.

The final Police Station and District always come from the Excel master —
AI cannot invent names.
"""

import re
import json

from common.matcher import find_district_in_excel
from common.ai_client import call_ai
from v2.config import COL_DISTRICT


def ai_infer_district(address, df, client):
    """
    Case 3 — Address only, neither PS nor District is known.

    Step 1: AI reasons over the address text and infers which district it
    belongs to, choosing only from the district list in the Excel master.
    No invented names — AI can only return districts that actually exist.

    Step 2 (ranking PS by real distance) is handled in engine.py by
    geopy_distance.rank_ps_by_distance() — no AI involved there.

    Returns:
        List of matched district name strings (up to 2), empty list on failure.
    """
    all_districts = sorted(df[COL_DISTRICT].unique().tolist())
    district_text = "\n".join(f"- {d}" for d in all_districts)

    prompt = f"""You are helping identify the correct Police Station for passport enrollment
verification in Hyderabad and Telangana.

You will be given:
1. An address.
2. A list of valid districts from an Excel master file.

IMPORTANT RULES:
- Use your knowledge of Hyderabad, Cyberabad and Telangana geography.
- Carefully analyse locality names, mandals, villages, suburbs and PIN codes.
- Locality names are often stronger indicators than district names in the address.
- Do NOT invent districts. You MUST choose only from the supplied district list.
- If genuinely uncertain, provide up to 2 districts.

ADDRESS:
{address.strip()}

AVAILABLE DISTRICTS:
{district_text}

Return ONLY JSON:
{{"districts": ["DISTRICT_NAME"]}}
or
{{"districts": ["DISTRICT_1", "DISTRICT_2"]}}"""

    inferred = []

    try:
        raw   = call_ai(prompt, client)
        match = re.search(r'\{.*\}', raw, re.DOTALL)

        if match:
            data         = json.loads(match.group())
            raw_districts = [str(d).strip().upper() for d in data.get("districts", [])]

            for d in raw_districts:
                if d in all_districts:
                    inferred.append(d)                      # exact match
                else:
                    hits = find_district_in_excel(d, df)    # fuzzy fallback
                    if hits:
                        inferred.append(hits[0]["district"])

            # Remove duplicates, preserve order
            inferred = list(dict.fromkeys(inferred))

    except Exception as e:
        print(f"  [WARN] AI district inference failed: {e}")
        return []

    if not inferred:
        print("  [WARN] AI could not determine a district from the address.")

    return inferred
