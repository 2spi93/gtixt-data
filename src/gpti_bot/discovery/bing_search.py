from __future__ import annotations

import os
from typing import Any, Dict, List

import requests


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_any(names: List[str]) -> str | None:
    for name in names:
        value = _env(name)
        if value:
            return value
    return None


def bing_search(query: str, *, count: int = 5, market: str = "en-US") -> List[Dict[str, Any]]:
    api_key = _env_any(["GPTI_BING_API_KEY", "BING_API_KEY"])
    endpoint = _env_any(["GPTI_BING_ENDPOINT", "BING_ENDPOINT"])
    debug = _env_any(["GPTI_BING_DEBUG"]) == "1"
    if not api_key or not endpoint:
        if debug:
            print("[bing] missing credentials")
        return []

    base = endpoint.rstrip("/")
    if "api.bing.microsoft.com" in base:
        url = base + "/v7.0/search"
    else:
        url = base + "/bing/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {
        "q": query,
        "count": count,
        "mkt": market,
        "responseFilter": "Webpages",
        "textDecorations": False,
        "textFormat": "Raw",
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=12)
        if resp.status_code >= 400:
            if debug:
                print(f"[bing] http={resp.status_code} query={query}")
                print(resp.text[:400])
            return []
    except Exception as exc:
        if debug:
            print(f"[bing] error query={query} err={exc}")
        return []

    try:
        data = resp.json()
    except Exception:
        if debug:
            print(f"[bing] invalid json query={query}")
            print(resp.text[:400])
        return []

    items = data.get("webPages", {}).get("value", [])
    if debug and not items:
        print(f"[bing] no results query={query}")
    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "name": item.get("name"),
                "url": item.get("url"),
                "snippet": item.get("snippet"),
            }
        )
    return results
