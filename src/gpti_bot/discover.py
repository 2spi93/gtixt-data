from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from .db import connect, slugify, FirmRow, upsert_firms


DEFAULT_SEED_JSON = "data/seeds/gpti_seed_pack_100.json"


# ---------------------------------------------------------
# Normalisation institutionnelle
# ---------------------------------------------------------

def _norm_model_type(v: str) -> str:
    """
    Normalise le type de modèle en 3 catégories institutionnelles :
    - CFD_FX
    - FUTURES
    - HYBRID
    """
    v = (v or "").strip().upper()

    if v in ("FX_CFD", "CFD", "FX", "CFD_FX"):
        return "CFD_FX"

    if v in ("FUTURES", "FUT"):
        return "FUTURES"

    if any(token in v for token in ("FOREX", "CFD")):
        return "CFD_FX"

    if "FUTURES" in v:
        return "FUTURES"

    if v in ("MULTI", "HYBRID"):
        return "HYBRID"

    if any(token in v for token in ("MULTI", "CRYPTO", "QUANT", "INSTITUTIONAL", "DIRECTORY", "STOCK")):
        return "HYBRID"

    return "HYBRID"


def _norm_status(v: str) -> str:
    """
    Normalise le statut :
    - candidate
    - watchlist
    - excluded
    """
    v = (v or "").strip().lower()

    if v == "candidate":
        return "candidate"

    if v in ("set_aside", "watchlist"):
        return "watchlist"

    if v in ("exclude", "excluded"):
        return "excluded"

    return "candidate"


def _jurisdiction_tier(jurisdiction: str | None) -> str | None:
    if not jurisdiction:
        return None
    value = jurisdiction.lower()
    tier_one = {
        "united states",
        "usa",
        "canada",
        "united kingdom",
        "uk",
        "australia",
        "new zealand",
        "singapore",
        "japan",
        "germany",
        "france",
        "netherlands",
        "switzerland",
        "austria",
        "sweden",
        "norway",
        "denmark",
        "finland",
        "ireland",
    }
    if any(value == item or item in value for item in tier_one):
        return "Tier 1"
    if "eu" in value or "europe" in value:
        return "Tier 2"
    if "offshore" in value or "islands" in value:
        return "Tier 3"
    return "Tier 2"


# ---------------------------------------------------------
# firm_id institutionnel
# ---------------------------------------------------------

def _firm_id_from(name: str, website: str) -> str:
    """
    Génère un firm_id stable :
    - priorité au domaine (ex: ftmo.com → ftmo)
    - fallback sur le nom
    """
    if website:
        try:
            host = urlparse(website).netloc.lower().replace("www.", "")
            if host:
                return slugify(host)
        except Exception:
            pass

    return slugify(name)


# ---------------------------------------------------------
# Chargement du seed
# ---------------------------------------------------------

def load_seed_records(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")

    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"Invalid JSON seed file: {path} ({e})")


# ---------------------------------------------------------
# Découverte institutionnelle
# ---------------------------------------------------------

def discover_from_seed(seed_path: str = DEFAULT_SEED_JSON) -> int:
    records = load_seed_records(seed_path)

    firms: List[FirmRow] = []

    for r in records:
        # Nom institutionnel
        name = (r.get("firm_name") or r.get("brand_name") or r.get("name") or "").strip()
        if not name:
            continue

        # URL institutionnelle
        website = (r.get("website") or r.get("website_root") or "").strip()

        jurisdiction = (r.get("country") or r.get("jurisdiction") or "").strip() or None
        jurisdiction_tier = _jurisdiction_tier(jurisdiction)

        model_type = _norm_model_type(r.get("model_type") or r.get("category") or "HYBRID")
        firms.append(
            FirmRow(
                firm_id=_firm_id_from(name, website),
                brand_name=name,
                website_root=website or "",
                model_type=model_type,
                status=_norm_status(r.get("status", "candidate")),
                jurisdiction=jurisdiction,
                jurisdiction_tier=jurisdiction_tier,
            )
        )

    with connect() as conn:
        return upsert_firms(conn, firms)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main(seed_path: str | None = None) -> int:
    path = seed_path or os.getenv("GPTI_SEED_FILE") or DEFAULT_SEED_JSON
    n = discover_from_seed(path)
    print(f"[discover] upserted {n} firms from {path}")
    return 0