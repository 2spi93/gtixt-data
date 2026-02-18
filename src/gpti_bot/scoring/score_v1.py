from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
import re

from ..db import connect


# ---------------------------------------------------------
# Load scoring spec from database
# ---------------------------------------------------------

def _load_scoring_spec() -> Dict[str, Any]:
    """Load the active scoring specification from score_version table."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT data_dictionary, weights, hierarchy
            FROM score_version
            WHERE is_active = true
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("No active scoring version found")

        data_dict, weights, hierarchy = row
        return {
            "data_dictionary": data_dict,
            "weights": weights,
            "hierarchy": hierarchy
        }


# ---------------------------------------------------------
# Utility functions for scoring
# ---------------------------------------------------------

def _bin_value(value: float, bins: List[float], labels: List[str], weights: List[float]) -> Tuple[str, float]:
    """Bin a numeric value and return the corresponding label and weight."""
    if value is None or not isinstance(value, (int, float)):
        return "na", 0.6  # NA policy (neutral tilt to avoid overly punitive gaps)

    for i, bin_threshold in enumerate(bins):
        if value <= bin_threshold:
            return labels[i], weights[i]

    # If value is greater than all bins, use the last one
    return labels[-1], weights[-1]


def _lookup_jurisdiction(country: str, matrix: Dict[str, Dict[str, float]]) -> float:
    """Look up jurisdiction risk score from the matrix."""
    if not country:
        return matrix.get("VERY_HIGH_RISK", {}).get("UNKNOWN", 0.10)

    country = country.upper()

    for risk_level, countries in matrix.items():
        if country in countries:
            return countries[country]

    # Default to offshore if not found
    return matrix.get("VERY_HIGH_RISK", {}).get("OFFSHORE", 0.10)


def _unwrap_datapoint(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("value"), dict):
        return value.get("value", {})
    if isinstance(value, dict):
        return value
    return {}


def _completeness_ratio(data: Dict[str, Any], keys: List[str]) -> Optional[float]:
    if not data or not keys:
        return None
    present = sum(1 for key in keys if data.get(key) not in (None, "", [], {}))
    return present / len(keys) if keys else None


def _rules_text_length(rules: Dict[str, Any]) -> Optional[int]:
    if not rules:
        return None
    parts: List[str] = []
    for key, value in rules.items():
        if key in ("_audit", "source_urls"):
            continue
        if isinstance(value, list):
            parts.extend([str(item) for item in value if item not in (None, "")])
            continue
        if value not in (None, ""):
            parts.append(str(value))
    text = " ".join(parts).strip()
    return len(text) if text else None


def _parse_percent(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", value)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    return None


def _map_change_frequency(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        mapping = {
            "low": 1,
            "rare": 1,
            "stable": 1,
            "medium": 2,
            "moderate": 2,
            "monthly": 2,
            "weekly": 3,
            "high": 4,
            "frequent": 4,
            "daily": 4,
        }
        for key, numeric in mapping.items():
            if key in lowered:
                return numeric
    return None


def _delay_days_from_frequency(freq: Optional[str]) -> Optional[int]:
    if not freq:
        return None
    f = str(freq).lower()
    if "on_demand" in f or "on demand" in f or "instant" in f:
        return 0
    if "biweekly" in f or "bi-weekly" in f or "fortnight" in f:
        return 14
    if "weekly" in f:
        return 7
    if "monthly" in f:
        return 30
    if "daily" in f:
        return 1
    return None


def _data_completeness_ratio(record: Dict[str, Any]) -> Optional[float]:
    keys = [
        "payout_frequency",
        "max_drawdown_rule",
        "daily_drawdown_rule",
        "rule_changes_frequency",
        "jurisdiction",
        "jurisdiction_tier",
        "headquarters",
        "founded_year",
    ]
    present = 0
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            present += 1
    return present / len(keys) if keys else None


def _derive_scoring_fields(record: Dict[str, Any]) -> None:
    rules = _unwrap_datapoint(record.get("rules"))
    pricing = _unwrap_datapoint(record.get("pricing"))

    payout_freq = pricing.get("payout_frequency") or rules.get("payout_frequency")
    payout_delay = _delay_days_from_frequency(payout_freq)
    if payout_delay is not None:
        record["payout.delay_days"] = payout_delay

    pricing_quality = _completeness_ratio(
        pricing,
        [
            "payout_frequency",
            "payout_split_pct",
            "refund_policy",
            "kyc_required",
            "challenge_fee_min",
            "challenge_fee_max",
        ],
    )
    if pricing_quality is None:
        pricing_quality = _completeness_ratio(
            rules,
            [
                "payout_split",
                "payout_frequency",
                "fees",
                "profit_target",
            ],
        )
    if pricing_quality is not None:
        record["payout.conditions_text_quality"] = round(pricing_quality, 3)

    rules_quality = _completeness_ratio(
        rules,
        [
            "brand_name",
            "platform",
            "instruments",
            "account_sizes",
            "profit_target",
            "daily_drawdown",
            "max_drawdown",
            "consistency_rule",
            "news_trading",
            "weekend_holding",
            "min_trading_days",
            "max_trading_days",
            "payout_split",
            "payout_frequency",
            "fees",
            "leverage",
            "notes",
        ],
    )
    if rules_quality is not None:
        record["rules.page_quality"] = round(rules_quality, 3)

    rules_length = _rules_text_length(rules)
    if rules_length is not None:
        record["rules.length_signal"] = rules_length

    daily_drawdown = _parse_percent(record.get("daily_drawdown_rule") or rules.get("daily_drawdown"))
    if daily_drawdown is not None:
        record["risk.max_daily_loss"] = daily_drawdown

    max_drawdown = _parse_percent(record.get("max_drawdown_rule") or rules.get("max_drawdown"))
    if max_drawdown is not None:
        record["risk.max_total_loss"] = max_drawdown

    change_frequency = _map_change_frequency(record.get("rule_changes_frequency") or rules.get("rule_changes_frequency"))
    if change_frequency is not None:
        record["rules.change_frequency"] = change_frequency

    jurisdiction = record.get("jurisdiction") or record.get("jurisdiction_tier")
    if jurisdiction:
        legal = record.get("legal") if isinstance(record.get("legal"), dict) else {}
        if not legal.get("company_registry_country"):
            legal["company_registry_country"] = jurisdiction
        record["legal"] = legal


def _compute_metric_score(metric_name: str, metric_def: Dict[str, Any], record: Dict[str, Any]) -> Tuple[float, bool]:
    """Compute score for a single metric based on its definition."""
    metric_type = metric_def.get("type", "binned")

    if metric_type == "binned":
        bins = metric_def.get("bins", [])
        labels = metric_def.get("labels", [])
        weights = metric_def.get("weights", [])

        if not bins or not labels or not weights:
            return 0.6, True  # NA

        value = record.get(metric_name)

        label, score = _bin_value(value, bins, labels, weights)
        return score, label == "na"

    elif metric_type == "jurisdiction_lookup":
        matrix_name = metric_def.get("matrix")
        if matrix_name:
            # Load matrix from spec
            spec = _load_scoring_spec()
            matrix = spec["data_dictionary"].get(matrix_name, {})
            country = record.get("legal", {}).get("company_registry_country")
            return _lookup_jurisdiction(country, matrix), country is None

    return 0.6, True  # Default NA


def _compute_pillar_score(
    pillar_def: Dict[str, Any],
    record: Dict[str, Any]
) -> Tuple[float, Dict[str, float], int, int]:
    """Compute score for a pillar by averaging its metrics."""
    metrics = pillar_def.get("metrics", {})
    if not metrics:
        return 0.5, {}, 0, 0  # NA

    scores = []
    metric_scores: Dict[str, float] = {}
    na_count = 0
    total_count = 0
    for metric_name, metric_def in metrics.items():
        score, is_na = _compute_metric_score(metric_name, metric_def, record)
        scores.append(score)
        metric_scores[metric_name] = round(score, 3)
        total_count += 1
        if is_na:
            na_count += 1

    return sum(scores) / len(scores) if scores else 0.5, metric_scores, na_count, total_count


# ---------------------------------------------------------
# Main scoring functions
# ---------------------------------------------------------

def compute_score_v1(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute v1.0 score for a single firm record.

    Returns a dict with pillar scores, overall score, and metadata.
    """
    spec = _load_scoring_spec()
    data_dict = spec["data_dictionary"]
    weights = spec["weights"]
    pillars = data_dict.get("pillars", {})

    pillar_scores: Dict[str, float] = {}
    metric_scores: Dict[str, float] = {}
    weighted_sum = 0.0
    total_weight = 0.0
    total_metrics = 0
    total_na = 0

    for pillar_key, pillar_def in pillars.items():
        pillar_score, pillar_metrics, na_count, metric_count = _compute_pillar_score(pillar_def, record)
        pillar_scores[pillar_key] = round(pillar_score, 3)
        metric_scores.update(pillar_metrics)
        total_metrics += metric_count
        total_na += na_count

        weight = weights.get(pillar_key, 0.0)
        weighted_sum += pillar_score * weight
        total_weight += weight

    overall_score = 100 * weighted_sum / total_weight if total_weight > 0 else 0.0

    na_rate = (total_na / total_metrics) * 100 if total_metrics > 0 else 0.0
    data_completeness = _data_completeness_ratio(record)
    if data_completeness is not None:
        metric_scores["data.completeness"] = round(data_completeness, 3)

    return {
        "score_overall": round(overall_score, 2),
        "pillar_scores": pillar_scores,
        "metric_scores": metric_scores,
        "na_rate": round(na_rate, 2),
        "data_completeness": round(data_completeness, 3) if data_completeness is not None else None,
        "version": "v1.0",
        "computed_at": None,  # Will be set by caller
    }


def score_snapshot_v1(snapshot_id: int) -> Dict[str, Any]:
    """
    Score all firms in a snapshot using v1.0 scoring.

    Returns summary statistics.
    """
    from ..minio import client as minio_client, get_bytes

    SNAP_BUCKET = "gpti-snapshots"

    # Load snapshot
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT bucket, object, sha256
            FROM snapshot_metadata
            WHERE id = %s
            """,
            (snapshot_id,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        bucket, object_path, sha256 = row

    m = minio_client()
    data = get_bytes(m, bucket, object_path)
    snap = json.loads(data.decode("utf-8"))

    records = snap.get("records", [])
    scored_records = []

    for rec in records:
        _derive_scoring_fields(rec)
        firm_id = rec["firm_id"]
        score_data = compute_score_v1(rec)
        data_completeness = score_data.get("data_completeness")
        if data_completeness is None:
            confidence = "medium"
        elif data_completeness >= 0.75:
            confidence = "high"
        elif data_completeness >= 0.45:
            confidence = "medium"
        else:
            confidence = "low"
        score_data["firm_id"] = firm_id
        scored_records.append(score_data)

        # Insert into database
        with connect() as conn:
            cur = conn.cursor()
            # Get snapshot_key
            cur.execute("SELECT snapshot_key FROM snapshot_metadata WHERE id = %s", (snapshot_id,))
            snapshot_key = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO snapshot_scores (snapshot_id, firm_id, snapshot_key, version_key, score, score_0_100, pillar_scores, metric_scores, na_rate, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (snapshot_id, firm_id) DO UPDATE SET
                    snapshot_key = EXCLUDED.snapshot_key,
                    version_key = EXCLUDED.version_key,
                    score = EXCLUDED.score,
                    score_0_100 = EXCLUDED.score_0_100,
                    pillar_scores = EXCLUDED.pillar_scores,
                    metric_scores = EXCLUDED.metric_scores,
                    na_rate = EXCLUDED.na_rate,
                    confidence = EXCLUDED.confidence
                """,
                (
                    snapshot_id,
                    firm_id,
                    snapshot_key,
                    score_data["version"],
                    json.dumps(score_data),
                    score_data["score_overall"],
                    json.dumps(score_data["pillar_scores"]),
                    json.dumps(score_data["metric_scores"]),
                    score_data["na_rate"],
                    confidence,
                )
            )
            conn.commit()

    # Summary
    scores = [r["score_overall"] for r in scored_records]
    summary = {
        "snapshot_id": snapshot_id,
        "firms_scored": len(scored_records),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "min_score": min(scores) if scores else 0.0,
        "max_score": max(scores) if scores else 0.0,
        "version": "v1.0"
    }

    # Insert audit record
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO snapshot_audit (snapshot_id, key, value)
            VALUES (%s, %s, %s)
            """,
            (snapshot_id, "score_v1.0", json.dumps(summary))
        )
        conn.commit()

    return summary