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
    "platforms": ["string"],
    "instruments": ["string"],
    "payout_split_pct": "number|null",
    "payout_frequency": "daily|weekly|biweekly|monthly|quarterly|annually|on_demand|null",
    "refund_policy": "yes|no|conditional|null",
    "kyc_required": "boolean|null",
    "notes": "string|null",
}

def extract_pricing(text: str, *, model: str = None) -> Dict[str, Any]:
    prompt = (
        SYSTEM_PROMPT
        + "\n\nSCHEMA:\n"
        + json.dumps(SCHEMA_HINT, indent=2)
        + "\n\nTEXT:\n"
        + text[:12000]
    )

    try:
        out = generate(prompt, model=model, temperature=0.0)
    except Exception as e:
        return {"error": "llm_call_failed", "detail": str(e)[:500]}

    raw = out.strip()

    try:
        data = json.loads(raw)
    except Exception:
        return {"error": "invalid_json", "raw": raw[:500]}

    normalized = {}
    list_fields = ["platforms", "instruments"]

    for key in SCHEMA_HINT.keys():
        v = data.get(key)

        if key in list_fields:
            normalized[key] = [str(x).strip() for x in v] if isinstance(v, list) else []
            continue

        if "number" in SCHEMA_HINT[key]:
            try:
                normalized[key] = float(v) if v is not None else None
            except Exception:
                normalized[key] = None
            continue

        if SCHEMA_HINT[key] == "boolean|null":
            normalized[key] = bool(v) if isinstance(v, bool) else None
            continue

        normalized[key] = v.strip() if isinstance(v, str) else None

    normalized["_audit"] = {
        "raw_preview": raw[:300],
        "model_used": model,
    }

    return normalized