from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

from gpti_bot.db import connect, fetch_firms, insert_datapoint
from gpti_bot.crawl import build_session, probe_url
from gpti_bot.external_sources import rank_candidates_diverse
from gpti_bot.discovery.web_search import web_search


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "y")


def _build_queries(brand_name: str, website_root: str | None) -> List[str]:
    base = (brand_name or "").strip()
    if not base:
        return []
    queries = [
        f"{base} prop firm rules",
        f"{base} prop firm pricing",
        f"{base} prop firm payout",
    ]
    if website_root:
        host = urlparse(website_root).netloc or website_root
        host = host.replace("https://", "").replace("http://", "").strip("/")
        if host:
            queries.append(f"site:{host} {base} rules")
    return queries


def run_access_check(
    *,
    limit: int = 20,
    include_aggregators: bool = True,
    include_bing: bool = True,
) -> Dict[str, Any]:
    allow_js = _env_bool("GPTI_ACCESS_JS_RENDER", True)
    min_html_bytes = _env_int("GPTI_ACCESS_MIN_HTML_BYTES", 400)
    agg_limit = _env_int("GPTI_ACCESS_AGGREGATOR_LIMIT", 3)
    bing_count = _env_int("GPTI_ACCESS_BING_COUNT", 4)
    bing_probe = _env_int("GPTI_ACCESS_BING_PROBE", 2)
    store_datapoints = _env_bool("GPTI_ACCESS_STORE", False)
    fail_hard = _env_bool("GPTI_ACCESS_FAIL_HARD", False)
    min_ok_ratio = float(os.getenv("GPTI_ACCESS_MIN_OK_RATIO", "0.5"))
    strict_mode = _env_bool("GPTI_ACCESS_STRICT", False)
    strict_consecutive = _env_int("GPTI_ACCESS_CONSEC_FAIL", 3)
    json_path = (os.getenv("GPTI_ACCESS_JSON_PATH") or "").strip()

    processed = 0
    ok_any = 0
    firm_ok = 0
    agg_ok = 0
    bing_ok = 0
    consecutive_fail = 0

    details: List[Dict[str, Any]] = []

    session = build_session()

    with connect() as conn:
        firms = fetch_firms(conn, limit=limit)

        for firm in firms:
            firm_id = firm.get("firm_id")
            brand_name = firm.get("brand_name") or ""
            website_root = firm.get("website_root") or ""
            processed += 1

            firm_result = probe_url(
                session,
                website_root,
                allow_js=allow_js,
                min_html_bytes=min_html_bytes,
            )
            firm_access_ok = bool(firm_result.get("ok"))

            aggregator_access_ok = False
            aggregator_urls: List[str] = []
            aggregator_probes: List[Dict[str, Any]] = []
            if include_aggregators:
                aggregator_urls = rank_candidates_diverse(
                    brand_name,
                    firm_id,
                    website_root,
                    limit=agg_limit,
                    per_slug=2,
                )
                for agg_url in aggregator_urls:
                    agg_result = probe_url(
                        session,
                        agg_url,
                        allow_js=allow_js,
                        min_html_bytes=min_html_bytes,
                    )
                    aggregator_probes.append({"url": agg_url, "probe": agg_result})
                    if agg_result.get("ok"):
                        aggregator_access_ok = True
                        break

            bing_access_ok = False
            bing_urls: List[str] = []
            bing_queries: List[str] = []
            bing_probes: List[Dict[str, Any]] = []
            if include_bing:
                for query in _build_queries(brand_name, website_root):
                    bing_queries.append(query)
                    results = web_search(query, max_results=bing_count)
                    for item in results:
                        url = item.get("url")
                        if not url or url in bing_urls:
                            continue
                        bing_urls.append(url)
                    if bing_urls:
                        break

                for url in bing_urls[:bing_probe]:
                    bing_result = probe_url(
                        session,
                        url,
                        allow_js=allow_js,
                        min_html_bytes=min_html_bytes,
                    )
                    bing_probes.append({"url": url, "probe": bing_result})
                    if bing_result.get("ok"):
                        bing_access_ok = True
                        break

            any_ok = firm_access_ok or aggregator_access_ok or bing_access_ok
            ok_any += 1 if any_ok else 0
            firm_ok += 1 if firm_access_ok else 0
            agg_ok += 1 if aggregator_access_ok else 0
            bing_ok += 1 if bing_access_ok else 0
            consecutive_fail = 0 if any_ok else consecutive_fail + 1

            print(
                "[access-check]"
                f" firm={firm_id}"
                f" firm_ok={int(firm_access_ok)}"
                f" agg_ok={int(aggregator_access_ok)}"
                f" bing_ok={int(bing_access_ok)}"
                f" url={website_root}"
            )

            details.append(
                {
                    "firm_id": firm_id,
                    "brand_name": brand_name,
                    "website_root": website_root,
                    "firm_ok": firm_access_ok,
                    "aggregator_ok": aggregator_access_ok,
                    "bing_ok": bing_access_ok,
                    "firm_probe": firm_result,
                    "aggregator_urls": aggregator_urls,
                    "aggregator_probes": aggregator_probes,
                    "bing_queries": bing_queries,
                    "bing_urls": bing_urls[:bing_probe],
                    "bing_probes": bing_probes,
                }
            )

            if store_datapoints:
                insert_datapoint(
                    conn,
                    firm_id=firm_id,
                    key="access_check_v1",
                    value_json={
                        "firm_ok": firm_access_ok,
                        "aggregator_ok": aggregator_access_ok,
                        "bing_ok": bing_access_ok,
                        "firm_probe": firm_result,
                        "aggregator_urls": aggregator_urls,
                        "aggregator_probes": aggregator_probes,
                        "bing_queries": bing_queries,
                        "bing_urls": bing_urls[:bing_probe],
                        "bing_probes": bing_probes,
                        "timestamp": time.time(),
                    },
                    value_text=None,
                    source_url=website_root,
                    evidence_hash=None,
                )

            if strict_mode and strict_consecutive > 0 and consecutive_fail >= strict_consecutive:
                print(
                    "[access-check] strict_stop"
                    f" consecutive_fail={consecutive_fail}"
                    f" threshold={strict_consecutive}"
                )
                break

    ratio = (ok_any / processed) if processed else 0.0
    summary = {
        "processed": processed,
        "ok_any": ok_any,
        "firm_ok": firm_ok,
        "aggregator_ok": agg_ok,
        "bing_ok": bing_ok,
        "ok_ratio": round(ratio, 3),
        "consecutive_fail": consecutive_fail,
        "strict_mode": strict_mode,
        "strict_consecutive": strict_consecutive,
    }
    print(f"[access-check] summary={summary}")

    if json_path:
        payload = {
            "summary": summary,
            "details": details,
        }
        try:
            folder = os.path.dirname(json_path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except Exception:
            pass

    if strict_mode and strict_consecutive > 0 and consecutive_fail >= strict_consecutive:
        return {"summary": summary, "status": "failed", "details": details}

    if fail_hard and ratio < min_ok_ratio:
        return {"summary": summary, "status": "failed", "details": details}

    return {"summary": summary, "status": "ok", "details": details}
