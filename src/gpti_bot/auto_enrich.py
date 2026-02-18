from __future__ import annotations

import os
from typing import Any, Dict, Iterable

from gpti_bot.db import connect, fetch_firms
from gpti_bot import crawl as crawl_mod
from gpti_bot.crawl import crawl_firm_by_id
from gpti_bot.agents.adaptive_enrichment_agent import run_targeted_enrichment_for_firm
from gpti_bot.extract_from_evidence import run_extract_from_evidence_for_firm


DATA_KEYS = {
    "rules_extracted_v0",
    "rules_extracted_from_home_v0",
    "pricing_extracted_v0",
    "pricing_extracted_from_home_v0",
}


def _has_any_data(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return any(
        payload.get(key) not in (None, "", [], {})
        for key in ("payout_frequency", "max_drawdown", "daily_drawdown", "payout_split_pct")
    )


def _firm_has_data(conn, firm_id: str) -> bool:
    sql = """
    SELECT key, value_json
    FROM datapoints
    WHERE firm_id = %s
      AND key = ANY(%s)
    ORDER BY created_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (firm_id, list(DATA_KEYS)))
        rows = cur.fetchall()
    for key, value in rows:
        if _has_any_data(value):
            return True
    return False


def run_auto_enrich_for_firm(firm_id: str) -> Dict[str, Any]:
    crawl_result = crawl_firm_by_id(firm_id)
    enrich_result = run_targeted_enrichment_for_firm(firm_id)
    evidence_result = run_extract_from_evidence_for_firm(firm_id)

    has_data = False
    with connect() as conn:
        has_data = _firm_has_data(conn, firm_id)

    deep_retry: dict | None = None
    if not has_data:
        overrides = {
            "CRAWL_DEPTH": int(os.getenv("GPTI_DEEP_CRAWL_DEPTH", "2")),
            "MAX_DEEP_LINKS": int(os.getenv("GPTI_DEEP_MAX_DEEP_LINKS", "60")),
            "MAX_PAGES_PER_FIRM": int(os.getenv("GPTI_DEEP_MAX_PAGES_PER_FIRM", "220")),
            "SITEMAP_MAX_URLS": int(os.getenv("GPTI_DEEP_SITEMAP_MAX_URLS", "120")),
            "MAX_RULE_PAGES": int(os.getenv("GPTI_DEEP_MAX_RULE_PAGES", "40")),
            "MAX_PRICING_PAGES": int(os.getenv("GPTI_DEEP_MAX_PRICING_PAGES", "40")),
            "MAX_JS_PAGES": int(os.getenv("GPTI_DEEP_MAX_JS_PAGES", "12")),
            "MIN_TEXT_CHARS": int(os.getenv("GPTI_DEEP_MIN_TEXT_CHARS", "400")),
            "HTTP_TIMEOUT_S": int(os.getenv("GPTI_DEEP_HTTP_TIMEOUT_S", "20")),
            "SLOW_DOMAIN_S": float(os.getenv("GPTI_DEEP_SLOW_DOMAIN_S", "18")),
        }
        previous = crawl_mod.apply_crawl_overrides(overrides)
        try:
            crawl_firm_by_id(firm_id)
        finally:
            crawl_mod.apply_crawl_overrides(previous)

        enrich_result_2 = run_targeted_enrichment_for_firm(firm_id)
        evidence_result_2 = run_extract_from_evidence_for_firm(firm_id)
        with connect() as conn:
            has_data = _firm_has_data(conn, firm_id)

        deep_retry = {
            "adaptive": enrich_result_2,
            "evidence": evidence_result_2,
            "has_data": has_data,
        }

    return {
        "firm_id": firm_id,
        "crawl": bool(crawl_result),
        "adaptive": enrich_result,
        "evidence": evidence_result,
        "has_data": has_data,
        "deep_retry": deep_retry,
    }


def run_auto_enrich(
    *,
    limit: int = 20,
    statuses: Iterable[str] = ("candidate", "watchlist", "eligible"),
) -> Dict[str, Any]:
    with connect() as conn:
        firms = fetch_firms(conn, statuses=statuses, limit=limit)

    results = []
    skipped = 0
    resume_enabled = os.getenv("GPTI_AUTO_RESUME", "0") == "1"
    with connect() as conn:
        for firm in firms:
            firm_id = firm.get("firm_id")
            if not firm_id:
                continue
            if resume_enabled and _firm_has_data(conn, firm_id):
                skipped += 1
                continue
            results.append(run_auto_enrich_for_firm(firm_id))

    processed = len(results)
    with_data = sum(1 for r in results if r.get("has_data"))
    return {
        "processed": processed,
        "skipped": skipped,
        "with_data": with_data,
        "without_data": processed - with_data,
    }
