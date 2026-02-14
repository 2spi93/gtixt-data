import json
import os
import re
from typing import Any, Dict, List

from gpti_bot.db import upsert_firms

def _slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:48] or "firm"

def discover_from_seed(seed_path: str, *, default_status: str = "watchlist", default_model_type: str = "CFD_FX") -> int:
    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows: List[dict[str, Any]] = []
    for item in data:
        brand = (item.get("brand_name") or item.get("brand") or "").strip()
        website = (item.get("website_root") or item.get("website") or "").strip()
        if not brand or not website:
            continue
        firm_id = item.get("firm_id") or _slugify(website.replace("https://","").replace("http://",""))
        rows.append({
            "firm_id": firm_id,
            "brand_name": brand,
            "website_root": website.rstrip("/"),
            "model_type": (item.get("model_type") or default_model_type).upper(),
            "status": (item.get("status") or default_status).lower(),
        })
    return upsert_firms(rows)
