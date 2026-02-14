from __future__ import annotations

import json
from typing import Any, Dict, List
import os

from ..db import connect


# ---------------------------------------------------------
# Oversight Gate Logic (deterministic quality firewall)
# ---------------------------------------------------------

FIRM_NA_RATE_THRESHOLD = 0.40  # Max NA rate for pass
GATE_MODE = os.getenv("GPTI_AGENT_C_MODE", "strict").lower()


def _check_firm_quality(firm_data: Dict[str, Any], datapoints: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Apply deterministic rules to decide pass/review for a firm.

    Returns dict with verdict, confidence, na_rate, reasons.
    """
    reasons = []
    na_rate = firm_data.get("na_rate", 0.0)
    confidence = firm_data.get("confidence", "high")

    if GATE_MODE == "soft":
        return {
            "verdict": "pass",
            "confidence": confidence,
            "na_rate": na_rate,
            "reasons": [],
        }

    # Rule 1: Low confidence -> review
    if confidence == "low":
        reasons.append("low_confidence")

    # Rule 2: High NA rate -> review
    if na_rate > FIRM_NA_RATE_THRESHOLD:
        reasons.append(f"na_rate_too_high_{na_rate:.2f}")

    # Rule 3: Technical errors -> review
    technical_errors = []
    for dp in datapoints:
        key = dp.get("key")
        value = dp.get("value") or {}
        if key in ("crawl_error", "http_error"):
            technical_errors.append("crawl_error")
        if key in ("rules_extract_error", "pricing_extract_error"):
            technical_errors.append("extraction_error")
        if key == "rules_extracted_v0" and isinstance(value, dict) and value.get("error"):
            technical_errors.append("extraction_error")

    if technical_errors:
        reasons.extend(technical_errors)

    # Rule 4: Missing key data -> review
    datapoint_keys = {dp.get("key") for dp in datapoints if dp.get("key")}
    has_rules = any(k in datapoint_keys for k in ("rules_extracted_v0", "rules_extracted_from_home_v0"))
    has_pricing = any(k in datapoint_keys for k in ("pricing_extracted_v0", "pricing_extracted_from_home_v0"))
    has_discovered_links = "discovered_links" in datapoint_keys

    if not has_rules and not has_pricing and not has_discovered_links:
        reasons.append("missing_key_data")

    # Verdict
    verdict = "review" if reasons else "pass"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "na_rate": na_rate,
        "reasons": reasons
    }


def apply_agent_c_gate(snapshot_id: int) -> Dict[str, Any]:
    """
    Apply Oversight Gate to all firms in a snapshot.

    Returns summary statistics.
    """
    with connect() as conn:
        cur = conn.cursor()

        # Get snapshot_key
        cur.execute("SELECT snapshot_key FROM snapshot_metadata WHERE id = %s", (snapshot_id,))
        snapshot_key = cur.fetchone()[0]

        # Get all scored firms
        cur.execute(
            """
            SELECT firm_id, score, na_rate, confidence
            FROM snapshot_scores
            WHERE snapshot_id = %s
            """,
            (snapshot_id,)
        )
        scored_firms = cur.fetchall()

        audit_records = []

        for firm_id, score_json, na_rate, confidence in scored_firms:
            # Get datapoints for this firm (check for any rules/pricing data)
            cur.execute(
                """
                SELECT key, value_json
                FROM datapoints
                WHERE firm_id = %s
                """,
                (firm_id,)
            )
            datapoint_rows = cur.fetchall()
            datapoints = [{"key": row[0], "value": row[1]} for row in datapoint_rows]

            firm_data = {
                "firm_id": firm_id,
                "na_rate": na_rate or 0.0,
                "confidence": confidence or "high"
            }

            gate_result = _check_firm_quality(firm_data, datapoints)

            # Insert audit record
            cur.execute(
                """
                INSERT INTO agent_c_audit (snapshot_key, firm_id, version_key, verdict, confidence, na_rate, reasons)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (snapshot_key, firm_id, version_key) DO UPDATE SET
                    verdict = EXCLUDED.verdict,
                    confidence = EXCLUDED.confidence,
                    na_rate = EXCLUDED.na_rate,
                    reasons = EXCLUDED.reasons
                """,
                (snapshot_key, firm_id, "v1.0", gate_result["verdict"], gate_result["confidence"], gate_result["na_rate"], json.dumps(gate_result["reasons"]))
            )

            audit_records.append(gate_result)

        conn.commit()

    # Summary
    pass_count = sum(1 for r in audit_records if r["verdict"] == "pass")
    review_count = sum(1 for r in audit_records if r["verdict"] == "review")

    return {
        "snapshot_id": snapshot_id,
        "snapshot_key": snapshot_key,
        "total_firms": len(audit_records),
        "pass_count": pass_count,
        "review_count": review_count,
        "pass_rate": pass_count / len(audit_records) if audit_records else 0.0
    }