from __future__ import annotations
import json
from typing import Any, Dict, List

from gpti_bot.llm.ollama_client import generate


# ---------------------------------------------------------
# Schema institutionnel
# ---------------------------------------------------------

RULE_SCHEMA = {
    "brand_name": "string",
    "platform": "string|null",
    "instruments": ["string"],
    "account_sizes": ["string"],
    "profit_target": "string|null",
    "daily_drawdown": "string|null",
    "max_drawdown": "string|null",
    "consistency_rule": "string|null",
    "news_trading": "string|null",
    "weekend_holding": "string|null",
    "min_trading_days": "string|null",
    "max_trading_days": "string|null",
    "payout_split": "string|null",
    "payout_frequency": "string|null",
    "fees": "string|null",
    "leverage": "string|null",
    "notes": "string|null",
    "source_urls": ["string"],
}

SYSTEM_PROMPT = """You extract prop firm rules from text.
Return STRICT JSON only (no markdown), matching the schema keys.
If unknown, use null or empty list.
Do NOT invent fields. Do NOT add commentary.
"""


# ---------------------------------------------------------
# Chunking
# ---------------------------------------------------------

def _chunk(text: str, max_chars: int = 9000) -> List[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


# ---------------------------------------------------------
# Extraction multi-pass institutionnelle
# ---------------------------------------------------------

def extract_rules_multi_pass(text: str, *, model: str | None = None) -> Dict[str, Any]:
    """
    Institutionnel :
    - chunk → LLM passes → merge robuste
    - jamais de crash
    - JSON strict
    - merge intelligent
    """

    chunks = _chunk(text, max_chars=9000)
    partials = []
    raw_outputs = []

    # Limite institutionnelle : max 4 passes
    for idx, ch in enumerate(chunks[:4]):
        prompt = (
            SYSTEM_PROMPT
            + "\n\nSCHEMA:\n"
            + json.dumps(RULE_SCHEMA)
            + "\n\nTEXT:\n"
            + ch
        )

        out = generate(prompt, model=model, temperature=0.0)
        raw_outputs.append(out[:500])

        try:
            parsed = json.loads(out)
            if isinstance(parsed, dict):
                partials.append(parsed)
        except Exception:
            # Retour institutionnel en cas d'échec
            return {
                "error": "llm_parse_failed",
                "detail": out[:500],
                "llm_passes": idx + 1,
            }

    # -----------------------------------------------------
    # Merge institutionnel
    # -----------------------------------------------------

    merged: Dict[str, Any] = {k: None for k in RULE_SCHEMA.keys()}
    merged["source_urls"] = []

    for p in partials:
        if not isinstance(p, dict):
            continue

        for k in RULE_SCHEMA.keys():
            v = p.get(k)

            # --- source_urls (union) ---
            if k == "source_urls":
                if isinstance(v, list):
                    for u in v:
                        if isinstance(u, str) and u not in merged["source_urls"]:
                            merged["source_urls"].append(u)
                continue

            # --- list fields ---
            if isinstance(v, list):
                cur = merged.get(k) or []
                if not isinstance(cur, list):
                    cur = []
                for item in v:
                    if isinstance(item, str) and item not in cur:
                        cur.append(item)
                merged[k] = cur
                continue

            # --- scalar fields ---
            if merged.get(k) in (None, "", []):
                merged[k] = v

    # Ensure lists exist
    for lk in ("instruments", "account_sizes", "source_urls"):
        if merged.get(lk) is None:
            merged[lk] = []

    # -----------------------------------------------------
    # Ajout audit interne
    # -----------------------------------------------------

    merged["_audit"] = {
        "llm_passes": len(partials),
        "raw_outputs_preview": raw_outputs,
    }

    return merged