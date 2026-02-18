from __future__ import annotations

import os
import json
import re
from typing import Any, Dict, List

from bs4 import BeautifulSoup

from gpti_bot.db import connect, insert_datapoint
from gpti_bot.minio import client as minio_client, get_bytes
from gpti_bot.crawl import html_to_text, _is_pdf, _pdf_to_text, _merge_missing_fields, _regex_extract_rules
from gpti_bot.agents.rules_extractor import extract_rules_multi_pass as extract_rules
from gpti_bot.agents.pricing_extractor import extract_pricing


def _split_object_path(raw_object_path: str) -> tuple[str, str]:
    parts = (raw_object_path or "").split("/", 1)
    if len(parts) != 2:
        raise ValueError("invalid raw_object_path")
    return parts[0], parts[1]


def _has_rules(payload: Dict[str, Any]) -> bool:
    return any(
        payload.get(key) not in (None, "", [], {})
        for key in ("payout_frequency", "max_drawdown", "daily_drawdown", "rule_changes_frequency")
    )


def _has_pricing(payload: Dict[str, Any]) -> bool:
    return any(
        payload.get(key) not in (None, "", [], {})
        for key in ("payout_frequency", "payout_split_pct", "challenge_fee_min", "challenge_fee_max")
    )


RULE_BLOCK_KEYWORDS = [
    "rules",
    "payout",
    "withdraw",
    "drawdown",
    "loss",
    "consistency",
    "scaling",
    "trading days",
    "terms",
]

PRICING_BLOCK_KEYWORDS = [
    "pricing",
    "fees",
    "challenge",
    "evaluation",
    "account size",
    "profit split",
    "refund",
]


def _semantic_blocks_from_html(raw: bytes, keywords: List[str]) -> str:
    try:
        soup = BeautifulSoup(raw.decode("utf-8", errors="ignore"), "lxml")
    except Exception:
        return ""

    text_blocks: list[str] = []
    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    for heading in headings:
        title = " ".join(heading.stripped_strings)
        if not title:
            continue
        low_title = title.lower()
        if not any(k in low_title for k in keywords):
            continue
        block_parts = [title]
        for sibling in heading.find_next_siblings():
            if sibling.name in ("h1", "h2", "h3", "h4"):
                break
            block_parts.append(" ".join(sibling.stripped_strings))
        block_text = " ".join([p for p in block_parts if p]).strip()
        if block_text:
            text_blocks.append(block_text)

    return " ".join(text_blocks).strip()


def _extract_text(raw: bytes, content_type: str, url: str, *, kind: str) -> str:
    if _is_pdf(content_type, url, raw):
        return _pdf_to_text(raw)
    if kind in ("rules", "pricing"):
        keywords = RULE_BLOCK_KEYWORDS if kind == "rules" else PRICING_BLOCK_KEYWORDS
        semantic = _semantic_blocks_from_html(raw, keywords)
        if semantic:
            return semantic
    return html_to_text(raw)


def _json_to_text(raw: bytes) -> str:
    try:
        parsed = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return ""
    return json.dumps(parsed, ensure_ascii=True)[:20000]


def _regex_extract_pricing(text: str) -> dict:
    lowered = text.lower()
    payout_frequency = _regex_extract_rules(text).get("payout_frequency")
    profit_split = None
    match = re.search(r"profit\s+split[^0-9]{0,12}(\d{1,3})\s*%", lowered)
    if match:
        try:
            profit_split = float(match.group(1))
        except ValueError:
            profit_split = None
    return {
        "payout_frequency": payout_frequency,
        "payout_split_pct": profit_split,
    }


def _fetch_evidence_rows(conn, firm_id: str) -> List[dict]:
    sql = """
    SELECT key, source_url, sha256, raw_object_path, created_at
    FROM evidence
    WHERE firm_id = %s
    AND key IN ('rules_html','rules_pdf','pricing_html','pricing_pdf','xhr_json','external_html','external_pdf')
      AND raw_object_path IS NOT NULL
    ORDER BY created_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (firm_id,))
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def run_extract_from_evidence_for_firm(firm_id: str) -> Dict[str, Any]:
    processed = 0
    extracted_rules = False
    extracted_pricing = False
    errors: list[str] = []

    with connect() as conn:
        rows = _fetch_evidence_rows(conn, firm_id)
        if not rows:
            return {"processed": 0, "rules": 0, "pricing": 0, "errors": 0, "note": "no_evidence"}

        m = minio_client()
        for row in rows:
            processed += 1
            try:
                bucket, obj = _split_object_path(row["raw_object_path"])
                raw = get_bytes(m, bucket, obj)
                evidence_key = row["key"]
                kind = _infer_kind_from_url(row.get("source_url") or "")
                if not kind:
                    kind = "rules" if evidence_key.startswith("rules") else "pricing"
                if evidence_key == "xhr_json":
                    text = _json_to_text(raw)
                else:
                    text = _extract_text(raw, "text/html", row["source_url"] or "", kind=kind)
                if not text or len(text) < 400:
                    continue

                if not extracted_rules and (evidence_key.startswith("rules") or evidence_key in ("xhr_json", "external_html", "external_pdf")):
                    rules = extract_rules(text)
                    rules = _merge_missing_fields(rules, _regex_extract_rules(text))
                    insert_datapoint(
                        conn,
                        firm_id=firm_id,
                        key="rules_extracted_v0",
                        value_json=rules,
                        value_text=None,
                        source_url=row["source_url"],
                        evidence_hash=row["sha256"],
                    )
                    extracted_rules = _has_rules(rules)

                if not extracted_pricing and (evidence_key.startswith("pricing") or evidence_key in ("xhr_json", "external_html", "external_pdf")):
                    pricing = extract_pricing(text)
                    pricing = _merge_missing_fields(pricing, _regex_extract_pricing(text))
                    insert_datapoint(
                        conn,
                        firm_id=firm_id,
                        key="pricing_extracted_v0",
                        value_json=pricing,
                        value_text=None,
                        source_url=row["source_url"],
                        evidence_hash=row["sha256"],
                    )
                    extracted_pricing = _has_pricing(pricing)

                if extracted_rules and extracted_pricing:
                    break
            except Exception as exc:
                errors.append(str(exc)[:200])

    return {
        "processed": processed,
        "rules": 1 if extracted_rules else 0,
        "pricing": 1 if extracted_pricing else 0,
        "errors": len(errors),
    }


def _infer_kind_from_url(url: str) -> str | None:
    low = (url or "").lower()
    if any(token in low for token in ("pricing", "fees", "challenge", "evaluation", "profit-split")):
        return "pricing"
    if any(token in low for token in ("rules", "drawdown", "payout", "withdraw", "terms")):
        return "rules"
    return None
