from __future__ import annotations
import json
import os
from typing import Any, Dict

from gpti_bot.llm.ollama_client import generate


SYSTEM_PROMPT = """You extract pricing and payout information from text.
Return STRICT JSON only (no markdown).
Unknown fields must be null.
Do NOT invent fields.
Do NOT add commentary.
"""

SCHEMA_HINT = {
    "currency": "USD|EUR|GBP|OTHER|null",
    "challenge_fee_min": "number|null",
    "challenge_fee_max": "number|null",
    "account_size_min": "number|null",
    "account_size_max": "number|null",
    "platforms": ["string"] ,
    "instruments": ["string"],
    "payout_split_pct": "number|null",
    "payout_frequency": "weekly|biweekly|monthly|on_demand|null",
    "refund_policy": "yes|no|conditional|null",
    "kyc_required": "boolean|null",
    "notes": "string|null",
}


def extract_pricing(text: str, *, model: str = None) -> Dict[str, Any]:
    """
    Extraction institutionnelle :
    - prompt strict
    - JSON strict
    - normalisation
    - audit interne
    """

    # ---------------------------------------------
    # Build prompt
    # ---------------------------------------------
    prompt = (
        SYSTEM_PROMPT
        + "\n\nSCHEMA:\n"
        + json.dumps(SCHEMA_HINT, indent=2)
        + "\n\nTEXT:\n"
        + text[:12000]
    )

    # ---------------------------------------------
    # Call LLM
    # ---------------------------------------------
    try:
        out = generate(prompt, model=model, temperature=0.0)
    except Exception as e:
        return {
            "error": "llm_call_failed",
            "detail": str(e)[:500],
        }

    raw = out.strip()

    # ---------------------------------------------
    # Parse JSON
    # ---------------------------------------------
    try:
        data = json.loads(raw)
    except Exception:
        return {
            "error": "invalid_json",
            "raw": raw[:500],
        }

    # ---------------------------------------------
    # Normalisation institutionnelle
    # ---------------------------------------------
    normalized = {}

    # Ensure lists
    list_fields = ["platforms", "instruments"]

    for key in SCHEMA_HINT.keys():
        v = data.get(key)

        # Lists
        if key in list_fields:
            if isinstance(v, list):
                normalized[key] = [str(x).strip() for x in v if isinstance(x, str)]
            else:
                normalized[key] = []
            continue

        # Numbers
        if "number" in SCHEMA_HINT[key]:
            try:
                normalized[key] = float(v) if v is not None else None
            except Exception:
                normalized[key] = None
            continue

        # Booleans
        if SCHEMA_HINT[key] == "boolean|null":
            normalized[key] = bool(v) if isinstance(v, bool) else None
            continue

        # Strings
        if isinstance(v, str):
            normalized[key] = v.strip()
        else:
            normalized[key] = None

    # ---------------------------------------------
    # Audit interne
    # ---------------------------------------------
    normalized["_audit"] = {
        "raw_preview": raw[:300],
        "model_used": model,
    }

    return normalized