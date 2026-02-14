from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import math
import json

# -----------------------------
# 1) Helpers déterministes
# -----------------------------

def clamp01(x: float) -> float:
    if x is None or math.isnan(x):
        return 0.5
    return max(0.0, min(1.0, x))

def score_identity(x: Any) -> float:
    try:
        return clamp01(float(x))
    except Exception:
        return 0.5

def score_inverse(x: Any) -> float:
    # x est supposé déjà en 0..1 (risk). inverse => 1-x
    return clamp01(1.0 - score_identity(x))

def score_bool(x: Any, true_score: float = 1.0, false_score: float = 0.0) -> float:
    if isinstance(x, bool):
        return true_score if x else false_score
    if isinstance(x, str):
        v = x.strip().lower()
        if v in ("true", "1", "yes", "y"):
            return true_score
        if v in ("false", "0", "no", "n"):
            return false_score
    return 0.5

def score_enum(x: Any, mapping: Dict[str, float]) -> float:
    if x is None:
        return 0.5
    key = str(x).strip()
    # case-insensitive match
    for k, s in mapping.items():
        if k.lower() == key.lower():
            return clamp01(float(s))
    return 0.5

def score_bins(value: Any, bins: List[float], labels: List[float], higher_is_better: bool = True) -> float:
    """
    bins = thresholds strictly increasing. labels = scores for each bucket.
    Example:
      bins=[3,7,14,30] => buckets:
        <=3, 4-7, 8-14, 15-30, >30  (5 buckets => labels len 5)
    """
    try:
        v = float(value)
    except Exception:
        return 0.5

    # find bucket index
    idx = 0
    while idx < len(bins) and v > bins[idx]:
        idx += 1
    # idx in [0..len(bins)]
    if idx >= len(labels):
        return 0.5

    # labels already encoded "institutional view" so no invert here
    return clamp01(float(labels[idx]))

# Jurisdiction scoring matrix v1 (transparent + simple)
JURISDICTION_MATRIX_V1 = {
    # Tier 1 (0.9)
    "united states": 0.9, "usa": 0.9, "us": 0.9,
    "united kingdom": 0.9, "uk": 0.9,
    "france": 0.9, "germany": 0.9, "netherlands": 0.9, "spain": 0.9, "italy": 0.9,
    "canada": 0.9, "australia": 0.9, "singapore": 0.9, "switzerland": 0.9,

    # Tier 2 (0.75)
    "uae": 0.75, "dubai": 0.75, "hong kong": 0.75, "new zealand": 0.75,

    # Tier 3 (0.6) - offshore / opaque jurisdictions (tu peux ajuster)
    "seychelles": 0.6, "st vincent": 0.6, "st. vincent": 0.6,
    "bvi": 0.6, "british virgin islands": 0.6,
    "cayman": 0.6, "cayman islands": 0.6,
    "belize": 0.6, "vanuatu": 0.6, "marshall islands": 0.6,
}

def score_jurisdiction_matrix_v1(x: Any) -> float:
    if not x:
        return 0.5
    k = str(x).strip().lower()
    # exact match first
    if k in JURISDICTION_MATRIX_V1:
        return JURISDICTION_MATRIX_V1[k]
    # partial match fallback
    for name, s in JURISDICTION_MATRIX_V1.items():
        if name in k:
            return s
    return 0.5

# -----------------------------
# 2) Fallback + NA policy
# -----------------------------

@dataclass(frozen=True)
class MetricResult:
    metric: str
    value: Any
    score: float
    source: str  # "primary" | "fallback:<metric>" | "NA"

def resolve_with_fallback(
    features: Dict[str, Any],
    metric: str,
    fallbacks: List[str],
) -> Tuple[Any, str]:
    if metric in features and features[metric] is not None:
        return features[metric], "primary"
    for fb in fallbacks:
        if fb in features and features[fb] is not None:
            return features[fb], f"fallback:{fb}"
    return None, "NA"

# -----------------------------
# 3) Core scoring (v1.0 spec)
# -----------------------------

def compute_score_v1(
    features: Dict[str, Any],
    spec: Dict[str, Any],  # active row from score_version.data_dictionary
    weights: Dict[str, float],  # score_version.weights
) -> Dict[str, Any]:
    na_value = float(spec["na_policy"]["na_value"])
    pillar_thr = float(spec["na_policy"]["pillar_na_rate_review_threshold"])
    firm_thr = float(spec["na_policy"]["firm_na_rate_review_threshold"])

    pillar_scores: Dict[str, float] = {}
    metric_scores: Dict[str, Dict[str, Any]] = {}

    total_metrics = 0
    total_na = 0

    for pillar_key, pillar in spec["pillars"].items():
        metrics = pillar["metrics"]
        pillar_metric_scores: List[float] = []
        pillar_metrics = 0
        pillar_na = 0

        for metric_name, meta in metrics.items():
            fallbacks = meta.get("fallback", [])
            value, source = resolve_with_fallback(features, metric_name, fallbacks)

            # score mapping
            s = na_value
            if source != "NA":
                mtype = meta["type"]
                score_map = meta["score_map"]

                if score_map == "identity":
                    s = score_identity(value)
                elif score_map == "inverse":
                    s = score_inverse(value)
                elif score_map == "jurisdiction_matrix_v1":
                    s = score_jurisdiction_matrix_v1(value)
                elif isinstance(score_map, dict) and mtype == "bool":
                    # expects {"true":1.0,"false":0.4} pattern sometimes
                    # use bool scoring if possible
                    if "true" in score_map and "false" in score_map:
                        s = score_bool(value, float(score_map["true"]), float(score_map["false"]))
                    else:
                        s = score_enum(value, {str(k): float(v) for k, v in score_map.items()})
                elif isinstance(score_map, dict) and mtype == "enum":
                    s = score_enum(value, {str(k): float(v) for k, v in score_map.items()})
                elif mtype in ("int", "hours", "pct", "usd"):
                    # bins → labels from score_map dict (explicit)
                    bins = meta.get("bins", [])
                    # We derive bucket scores in fixed order matching your v1.0 JSON
                    # For readability: explicit label list per our v1.0 choices:
                    # delay_days: <=3, 4-7, 8-14, 15-30, >30
                    if metric_name in ("payout.delay_days",):
                        labels = [1.0, 0.8, 0.6, 0.4, 0.2]
                        s = score_bins(value, bins, labels)
                    elif metric_name in ("support.response_time",):
                        labels = [1.0, 0.8, 0.6, 0.4, 0.2]
                        s = score_bins(value, bins, labels)
                    elif metric_name in ("risk.max_daily_loss",):
                        # bins [1,2,3,5] => <=1, 1-2, 2-3, 3-5, >5
                        # Our mapping wants >=5 best. Since bins are ascending, we just encode labels accordingly:
                        # <=1 ->0.2, (1,2]->0.4, (2,3]->0.6, (3,5]->0.8, >5->1.0
                        labels = [0.2, 0.4, 0.6, 0.8, 1.0]
                        s = score_bins(value, bins, labels)
                    elif metric_name in ("risk.max_total_loss",):
                        # bins [2,4,6,10] => <=2, 2-4, 4-6, 6-10, >10
                        labels = [0.2, 0.4, 0.6, 0.8, 1.0]
                        s = score_bins(value, bins, labels)
                    elif metric_name in ("pricing.fees",):
                        # bins [50,100,200,400] => <=50, 50-100, 100-200, 200-400, >400
                        labels = [1.0, 0.8, 0.6, 0.4, 0.2]
                        s = score_bins(value, bins, labels)
                    else:
                        s = na_value
                else:
                    s = na_value

            if source == "NA":
                pillar_na += 1
                total_na += 1

            pillar_metrics += 1
            total_metrics += 1
            pillar_metric_scores.append(float(s))

            metric_scores[metric_name] = {
                "value": value,
                "score": float(s),
                "source": source
            }

        # pillar score = mean
        pillar_score = sum(pillar_metric_scores) / max(1, len(pillar_metric_scores))
        pillar_scores[pillar_key] = float(pillar_score)

        pillar_na_rate = pillar_na / max(1, pillar_metrics)
        metric_scores[pillar_key + ".__na_rate"] = {"value": pillar_na_rate, "score": pillar_na_rate, "source": "computed"}

    # aggregate weighted score
    weighted = 0.0
    for p, w in weights.items():
        weighted += float(w) * float(pillar_scores.get(p, 0.5))

    na_rate = total_na / max(1, total_metrics)

    # confidence
    if na_rate <= 0.20:
        confidence = "high"
    elif na_rate <= firm_thr:
        confidence = "medium"
    else:
        confidence = "low"

    verdict = "pass" if confidence != "low" else "review"

    return {
        "score_0_100": float(100.0 * weighted),
        "pillar_scores": pillar_scores,
        "metric_scores": metric_scores,
        "na_rate": float(na_rate),
        "confidence": confidence,
        "verdict": verdict,
    }

# -----------------------------
# 4) Runner DB (snapshot_key)
# -----------------------------
# Assumes you already stored v1.0 in score_version with is_active=true.

SCORE_SQL_UPSERT = """
INSERT INTO snapshot_scores
(snapshot_key, firm_id, version_key, score_0_100, pillar_scores, metric_scores, na_rate, confidence, verdict)
VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
ON CONFLICT (snapshot_key, firm_id, version_key) DO UPDATE SET
  score_0_100 = EXCLUDED.score_0_100,
  pillar_scores = EXCLUDED.pillar_scores,
  metric_scores = EXCLUDED.metric_scores,
  na_rate = EXCLUDED.na_rate,
  confidence = EXCLUDED.confidence,
  verdict = EXCLUDED.verdict,
  created_at = now();
"""

def score_snapshot_v1(db_conn, snapshot_key: str) -> int:
    """
    Deterministic scoring for all firms in snapshot_key.
    Expects a table datapoints(firm_id,key,value_json,source_url,captured_at) and firms(firm_id,model_type,status,...).
    """
    with db_conn.cursor() as cur:
        # active spec
        cur.execute("""
          SELECT version_key, data_dictionary, weights
          FROM score_version
          WHERE is_active = true
          ORDER BY created_at DESC
          LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            raise RuntimeError("No active score_version found (is_active=true).")

        version_key, data_dictionary, weights = row
        spec = data_dictionary
        w = weights

        # load firms (candidate+watchlist) - adjust to your policy
        cur.execute("""
          SELECT firm_id
          FROM firms
          WHERE status IN ('candidate','watchlist')
        """)
        firms = [r[0] for r in cur.fetchall()]

        n = 0
        for firm_id in firms:
            # last datapoints per key for this firm
            cur.execute("""
              SELECT key, value_json
              FROM (
                SELECT key, value_json,
                       row_number() OVER (PARTITION BY key ORDER BY captured_at DESC) AS rn
                FROM datapoints
                WHERE firm_id = %s
              ) t
              WHERE rn = 1
            """, (firm_id,))
            features = {}
            for k, v in cur.fetchall():
                # flatten: if extractor already outputs normalized keys, merge them
                # Otherwise store raw by key.
                if isinstance(v, dict):
                    # merge dict payload (recommended)
                    for kk, vv in v.items():
                        features[kk] = vv
                else:
                    features[k] = v

            # make sure model_type is available if not in datapoints
            cur.execute("SELECT model_type FROM firms WHERE firm_id=%s", (firm_id,))
            mt = cur.fetchone()
            if mt:
                features["model_type"] = mt[0]

            res = compute_score_v1(features, spec, w)

            cur.execute(
                SCORE_SQL_UPSERT,
                (
                    snapshot_key, firm_id, version_key,
                    res["score_0_100"],
                    json.dumps(res["pillar_scores"]),
                    json.dumps(res["metric_scores"]),
                    res["na_rate"],
                    res["confidence"],
                    res["verdict"],
                )
            )
            n += 1

        db_conn.commit()
        return n
