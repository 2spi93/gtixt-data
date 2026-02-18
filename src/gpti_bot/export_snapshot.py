from __future__ import annotations

import json
import hashlib
import datetime as dt
import os
from pathlib import Path
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

from .db import connect
from .minio import client as minio_client, put_bytes

SNAP_BUCKET = "gpti-snapshots"
SNAP_VERSION = "universe_v0.1"
PUBLIC_VERDICTS = [
    v.strip()
    for v in os.getenv("GPTI_PUBLIC_VERDICTS", "pass,review").split(",")
    if v.strip()
]


# ---------------------------------------------------------
# JSON encoder for audit-friendly serialization
# ---------------------------------------------------------

def _json_default(o):
    # SAFE, audit-friendly: Decimal -> str to avoid float precision loss
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _latest_datapoint(conn, firm_id: str, key: str) -> dict | None:
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT value_json, source_url, evidence_hash
            FROM datapoints
            WHERE firm_id=%s AND key=%s
            ORDER BY created_at DESC
            LIMIT 1
        """, (firm_id, key))
    except Exception:
        cur.execute("""
            SELECT value_json, source_url, evidence_hash
            FROM datapoints
            WHERE firm_id=%s AND key=%s
            ORDER BY ctid DESC
            LIMIT 1
        """, (firm_id, key))

    row = cur.fetchone()
    if not row:
        return None

    return {
        "value": row[0],
        "source_url": row[1],
        "evidence_hash": row[2],
    }


def _read_overrides_file(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        if str(key).startswith("_"):
            continue
        cleaned[str(key).lower()] = value
    return cleaned


def _load_overrides() -> dict[str, Any]:
    base = os.getenv("GPTI_OVERRIDES_DIR", "/opt/gpti/gpti-site/data")
    auto_path = os.path.join(base, "firm-overrides.auto.json")
    manual_path = os.path.join(base, "firm-overrides.json")
    auto = _read_overrides_file(auto_path)
    manual = _read_overrides_file(manual_path)
    return {**auto, **manual}


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _apply_overrides(record: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    firm_id = str(record.get("firm_id") or "").lower()
    if not firm_id:
        return record
    override = overrides.get(firm_id)
    if not isinstance(override, dict):
        return record
    merged = dict(record)
    for key, value in override.items():
        if not _is_empty_value(value):
            merged[key] = value
    return merged


def _parse_numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        trimmed = value.strip().replace("%", "")
        if not trimmed:
            return None
        try:
            return float(trimmed)
        except ValueError:
            return None
    return None


def _unwrap_datapoint_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if isinstance(value.get("rules"), dict):
            return value.get("rules", {})
        if isinstance(value.get("value"), dict):
            return value.get("value", {})
        return value
    return {}


def _load_latest_datapoints(conn, firm_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not firm_ids:
        return {}
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT ON (firm_id, key) firm_id, key, value_json
        FROM datapoints
        WHERE firm_id = ANY(%s)
          AND key = ANY(%s)
        ORDER BY firm_id, key, created_at DESC
        """,
        (
            firm_ids,
            [
                "rules_extracted_v0",
                "rules_extracted_from_home_v0",
                "pricing_extracted_v0",
                "pricing_extracted_from_home_v0",
            ],
        ),
    )
    rows = cur.fetchall()
    payload: dict[str, dict[str, Any]] = {}
    for firm_id, key, value_json in rows:
        payload.setdefault(firm_id, {})[key] = value_json
    return payload


def _pick_pillar_score(pillar_scores: dict[str, Any] | None, keys: list[str]) -> float | None:
    if not pillar_scores:
        return None
    lowered = {str(k).lower(): v for k, v in pillar_scores.items()}
    for key in keys:
        for k, v in lowered.items():
            if key in k:
                parsed = _parse_numeric(v)
                if parsed is not None:
                    return parsed
    return None


def _pick_metric_score(metric_scores: dict[str, Any] | None, keys: list[str]) -> float | None:
    if not metric_scores:
        return None
    lowered = {str(k).lower(): v for k, v in metric_scores.items()}
    for key in keys:
        value = lowered.get(key)
        parsed = _parse_numeric(value)
        if parsed is not None:
            return parsed
    return None


def _infer_jurisdiction_tier(jurisdiction: str | None) -> str | None:
    if not jurisdiction:
        return None
    value = jurisdiction.lower()
    if "global" in value:
        return None
    tier_one = [
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
    ]
    if any(country in value for country in tier_one):
        return "Tier 1"
    if "eu" in value or "europe" in value:
        return "Tier 2"
    if "offshore" in value or "islands" in value:
        return "Tier 3"
    return "Tier 2"


def _infer_jurisdiction_from_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        url = value if value.startswith("http") else f"https://{value}"
        parsed = urlparse(url)
        host = parsed.hostname or ""
        tld = ".".join(host.split(".")[-2:])
        tld_map = {
            "co.uk": "United Kingdom",
            "uk": "United Kingdom",
            "com.au": "Australia",
            "au": "Australia",
            "ca": "Canada",
            "us": "United States",
            "ie": "Ireland",
            "fr": "France",
            "de": "Germany",
            "es": "Spain",
            "it": "Italy",
            "nl": "Netherlands",
            "be": "Belgium",
            "se": "Sweden",
            "no": "Norway",
            "dk": "Denmark",
            "fi": "Finland",
            "ch": "Switzerland",
            "at": "Austria",
            "pl": "Poland",
            "cz": "Czech Republic",
            "pt": "Portugal",
            "sg": "Singapore",
            "hk": "Hong Kong",
            "jp": "Japan",
            "cn": "China",
            "in": "India",
            "br": "Brazil",
            "mx": "Mexico",
            "za": "South Africa",
            "ae": "United Arab Emirates",
            "eu": "European Union",
            "io": "International",
            "com": "Global",
            "net": "Global",
            "org": "Global",
            "co": "Global",
        }
        return tld_map.get(tld) or tld_map.get(host.split(".")[-1])
    except Exception:
        return None


def _compute_data_completeness(record: dict[str, Any]) -> tuple[float, str]:
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
    ratio = present / len(keys) if keys else 0.0
    if ratio >= 0.75:
        badge = "complete"
    elif ratio >= 0.45:
        badge = "partial"
    else:
        badge = "incomplete"
    return round(ratio, 3), badge


def _apply_derived_fields(record: dict[str, Any]) -> dict[str, Any]:
    metric_scores = record.get("metric_scores")
    pillar_scores = record.get("pillar_scores")

    payout_reliability = record.get("payout_reliability")
    if payout_reliability is None:
        payout_reliability = _pick_pillar_score(pillar_scores, ["payout"]) or _pick_metric_score(
            metric_scores, ["payout_reliability", "payout.reliability"]
        )

    risk_model_integrity = record.get("risk_model_integrity")
    if risk_model_integrity is None:
        risk_model_integrity = _pick_pillar_score(pillar_scores, ["risk"]) or _pick_metric_score(
            metric_scores, ["risk_model_integrity", "risk.model_integrity"]
        )

    operational_stability = record.get("operational_stability")
    if operational_stability is None:
        operational_stability = (
            _pick_pillar_score(pillar_scores, ["operational", "stability", "reputation", "support"])
            or _pick_metric_score(metric_scores, ["operational_stability", "operational.stability"])
        )

    historical_consistency = record.get("historical_consistency")
    if historical_consistency is None:
        historical_consistency = _pick_pillar_score(pillar_scores, ["historical", "consistency"]) or _pick_metric_score(
            metric_scores, ["historical_consistency", "historical.consistency"]
        )

    jurisdiction = record.get("jurisdiction")
    if not jurisdiction:
        inferred = _infer_jurisdiction_from_url(record.get("website_root"))
        if inferred:
            jurisdiction = inferred
            record = dict(record)
            record["jurisdiction"] = inferred

    jurisdiction_tier = record.get("jurisdiction_tier")
    if jurisdiction_tier is None:
        jurisdiction_tier = _infer_jurisdiction_tier(jurisdiction)
    headquarters = record.get("headquarters")
    if not headquarters:
        if jurisdiction and "global" not in str(jurisdiction).lower():
            headquarters = jurisdiction
    if jurisdiction_tier is None:
        jurisdiction_tier = _infer_jurisdiction_tier(headquarters)

    na_policy_applied = record.get("na_policy_applied")
    if na_policy_applied is None and record.get("na_rate") is not None:
        na_policy_applied = True

    enriched = dict(record)
    if payout_reliability is not None:
        enriched["payout_reliability"] = payout_reliability
    if risk_model_integrity is not None:
        enriched["risk_model_integrity"] = risk_model_integrity
    if operational_stability is not None:
        enriched["operational_stability"] = operational_stability
    if historical_consistency is not None:
        enriched["historical_consistency"] = historical_consistency
    if jurisdiction_tier is not None:
        enriched["jurisdiction_tier"] = jurisdiction_tier
    if headquarters is not None:
        enriched["headquarters"] = headquarters
    if na_policy_applied is not None:
        enriched["na_policy_applied"] = na_policy_applied
    data_completeness, data_badge = _compute_data_completeness(enriched)
    enriched["data_completeness"] = data_completeness
    enriched["data_badge"] = data_badge
    return enriched


def _compute_percentile(scores: list[float], value: float) -> int | None:
    if not scores:
        return None
    sorted_scores = sorted(scores)
    rank = sum(1 for score in sorted_scores if score <= value)
    if len(sorted_scores) == 1:
        return 50
    pr = (rank - 1) / (len(sorted_scores) - 1)
    return round((1 - pr) * 100)


# ---------------------------------------------------------
# Public snapshot builder (Oversight Gate gated)
# ---------------------------------------------------------

def build_public_snapshot(snapshot_id: int, snapshot_key: str, version_key: str = "v1.0") -> dict[str, Any]:
    with connect() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='firms'
        """)
        firm_cols = {row[0] for row in cur.fetchall()}
        firm_fields = [
            "brand_name",
            "name",
            "website_root",
            "model_type",
            "status",
            "jurisdiction",
            "jurisdiction_tier",
            "logo_url",
            "founded_year",
        ]
        firm_select = ",\n              ".join(
            f"f.{col}" if col in firm_cols else f"NULL AS {col}"
            for col in firm_fields
        )

        cur.execute("""
            SELECT 1
            FROM information_schema.tables
            WHERE table_name='firm_profiles'
        """)
        has_firm_profiles = cur.fetchone() is not None

        if has_firm_profiles:
            fp_select = """
              fp.executive_summary,
              fp.status_gtixt,
              fp.data_sources,
              fp.verification_hash,
              fp.last_updated,
              fp.audit_verdict,
              fp.oversight_gate_verdict
            """
            fp_join = "LEFT JOIN firm_profiles fp ON fp.firm_id = p.firm_id"
        else:
            fp_select = """
              NULL AS executive_summary,
              NULL AS status_gtixt,
              NULL AS data_sources,
              NULL AS verification_hash,
              NULL AS last_updated,
              NULL AS audit_verdict,
              NULL AS oversight_gate_verdict
            """
            fp_join = ""

        # Get publishable firms
        cur.execute(
            f"""
                        SELECT
              p.firm_id,
              p.score_0_100,
              p.pillar_scores,
              p.metric_scores,
              p.na_rate,
              p.confidence,
                            a.verdict,
              a.reasons,
              {firm_select},
              {fp_select}
            FROM snapshot_scores p
            JOIN agent_c_audit a
                ON a.snapshot_key = p.snapshot_key
             AND a.firm_id = p.firm_id
             AND a.version_key = p.version_key
            LEFT JOIN firms f ON f.firm_id = p.firm_id
            {fp_join}
            WHERE p.snapshot_id = %s
                AND p.snapshot_key = %s
                AND p.version_key = %s
                                AND a.verdict = ANY(%s)
            """,
                        (snapshot_id, snapshot_key, version_key, PUBLIC_VERDICTS)
        )
        rows = cur.fetchall()

        datapoints = _load_latest_datapoints(conn, [row[0] for row in rows])

        overrides = _load_overrides()
        records = []
        for (
            firm_id,
            score_0_100,
            pillar_scores,
            metric_scores,
            na_rate,
            confidence,
            verdict,
            reasons,
            brand_name,
            name,
            website_root,
            model_type,
            status,
            jurisdiction,
            jurisdiction_tier,
            logo_url,
            founded_year,
            executive_summary,
            status_gtixt,
            data_sources,
            verification_hash,
            last_updated,
            audit_verdict,
            oversight_gate_verdict,
        ) in rows:
            firm_datapoints = datapoints.get(firm_id, {})
            rules_value = firm_datapoints.get("rules_extracted_v0") or firm_datapoints.get("rules_extracted_from_home_v0")
            pricing_value = firm_datapoints.get("pricing_extracted_v0") or firm_datapoints.get("pricing_extracted_from_home_v0")
            rules_data = _unwrap_datapoint_value(rules_value)
            pricing_data = _unwrap_datapoint_value(pricing_value)
            display_name = brand_name or name
            payout_frequency = pricing_data.get("payout_frequency") or rules_data.get("payout_frequency")
            max_drawdown_rule = rules_data.get("max_drawdown_rule") or rules_data.get("max_drawdown")
            daily_drawdown_rule = rules_data.get("daily_drawdown_rule") or rules_data.get("daily_drawdown")
            rule_changes_frequency = rules_data.get("rule_changes_frequency") or rules_data.get("rule_change_frequency")
            record = {
                "firm_id": firm_id,
                "name": display_name,
                "firm_name": display_name,
                "website_root": website_root,
                "model_type": model_type,
                "status": status,
                "jurisdiction": jurisdiction,
                "jurisdiction_tier": jurisdiction_tier,
                "logo_url": logo_url,
                "founded_year": founded_year,
                "status_gtixt": status_gtixt,
                "executive_summary": executive_summary,
                "payout_frequency": payout_frequency,
                "max_drawdown_rule": max_drawdown_rule,
                "daily_drawdown_rule": daily_drawdown_rule,
                "rule_changes_frequency": rule_changes_frequency,
                "score_0_100": float(score_0_100) if score_0_100 is not None else None,
                "pillar_scores": pillar_scores,
                "metric_scores": metric_scores,
                "na_rate": float(na_rate) if na_rate is not None else None,
                "confidence": confidence,
                "gtixt_status": verdict,
                "agent_c_reasons": reasons,
                "oversight_gate_verdict": oversight_gate_verdict or verdict or "pass",
                "audit_verdict": audit_verdict,
                "data_sources": data_sources,
                "verification_hash": verification_hash,
                "last_updated": last_updated,
                "snapshot_history": [],
            }
            record = _apply_overrides(record, overrides)
            record = _apply_derived_fields(record)
            records.append(record)

        score_values: list[float] = []
        scores_by_model: dict[str, list[float]] = {}
        scores_by_jurisdiction: dict[str, list[float]] = {}
        for record in records:
            score_value = _parse_numeric(record.get("score_0_100") or record.get("score"))
            if score_value is None:
                continue
            score_values.append(score_value)
            model_type = (record.get("model_type") or "").strip()
            if model_type:
                scores_by_model.setdefault(model_type, []).append(score_value)
            jurisdiction = (record.get("jurisdiction") or "").strip()
            if jurisdiction:
                scores_by_jurisdiction.setdefault(jurisdiction, []).append(score_value)

        for record in records:
            score_value = _parse_numeric(record.get("score_0_100") or record.get("score"))
            if score_value is None:
                continue
            if record.get("percentile_vs_universe") is None:
                record["percentile_vs_universe"] = _compute_percentile(score_values, score_value)
            model_type = (record.get("model_type") or "").strip()
            if record.get("percentile_vs_model_type") is None and model_type in scores_by_model:
                record["percentile_vs_model_type"] = _compute_percentile(scores_by_model[model_type], score_value)
            jurisdiction = (record.get("jurisdiction") or "").strip()
            if record.get("percentile_vs_jurisdiction") is None and jurisdiction in scores_by_jurisdiction:
                record["percentile_vs_jurisdiction"] = _compute_percentile(scores_by_jurisdiction[jurisdiction], score_value)

        meta = {
            "snapshot_version": f"{SNAP_VERSION}_public",
            "generated_at_utc": _now_utc(),
            "count": len(records),
            "gated_by": ",".join(PUBLIC_VERDICTS) or "agent_c",
            "version_key": version_key,
        }

        return {"meta": meta, "records": records}

def build_snapshot(limit: int | None = None) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='firms'
        """)
        cols = {row[0] for row in cur.fetchall()}
        select_cols = ["firm_id"]
        optional_cols = [
            "name",
            "brand_name",
            "website_root",
            "model_type",
            "status",
            "jurisdiction",
            "jurisdiction_tier",
        ]
        for col in optional_cols:
            if col in cols:
                select_cols.append(col)

        sql = f"SELECT {', '.join(select_cols)} FROM firms ORDER BY firm_id"

        if limit:
            sql += f" LIMIT {int(limit)}"

        cur.execute(sql)
        rows = cur.fetchall()

        records = []

        for row in rows:
            row_data = dict(zip(select_cols, row))
            firm_id = row_data.get("firm_id")
            name = row_data.get("brand_name") or row_data.get("name")
            website_root = row_data.get("website_root")
            model_type = row_data.get("model_type")
            status = row_data.get("status")
            jurisdiction = row_data.get("jurisdiction")
            jurisdiction_tier = row_data.get("jurisdiction_tier")

            rules = (
                _latest_datapoint(conn, firm_id, "rules_extracted_v0")
                or _latest_datapoint(conn, firm_id, "rules_extracted_from_home_v0")
            )

            pricing = (
                _latest_datapoint(conn, firm_id, "pricing_extracted_v0")
                or _latest_datapoint(conn, firm_id, "pricing_extracted_from_home_v0")
            )

            records.append({
                "firm_id": firm_id,
                "name": name,
                "website_root": website_root,
                "model_type": model_type,
                "status": status,
                "jurisdiction": jurisdiction,
                "jurisdiction_tier": jurisdiction_tier,
                "rules": rules,
                "pricing": pricing,
            })

        meta = {
            "snapshot_version": SNAP_VERSION,
            "generated_at_utc": _now_utc(),
            "count": len(records),
        }

        return {"meta": meta, "records": records}


# ---------------------------------------------------------
# Upload to MinIO
# ---------------------------------------------------------

def upload_snapshot(snapshot: dict[str, Any], *, prefix: str = SNAP_VERSION) -> dict[str, str]:
    m = minio_client()

    try:
        if not m.bucket_exists(SNAP_BUCKET):
            m.make_bucket(SNAP_BUCKET)
    except Exception:
        pass

    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, default=_json_default).encode("utf-8")
    digest = _sha256(payload)

    ts = snapshot["meta"]["generated_at_utc"].replace(":", "").replace("-", "")
    key = f"{prefix}/{ts}_{digest[:12]}.json"

    put_bytes(m, SNAP_BUCKET, key, payload, content_type="application/json")

    manifest = json.dumps({
        "sha256": digest,
        "object": f"{SNAP_BUCKET}/{key}",
        "version": SNAP_VERSION,
        "generated_at": snapshot["meta"]["generated_at_utc"],
    }, indent=2).encode("utf-8")

    put_bytes(
        m,
        SNAP_BUCKET,
        f"{prefix}/{ts}_{digest[:12]}.manifest.json",
        manifest,
        content_type="application/json",
    )

    return {"bucket": SNAP_BUCKET, "object": key, "sha256": digest}


# ---------------------------------------------------------
# Save metadata in Postgres
# ---------------------------------------------------------

def save_snapshot_metadata(snapshot_key: str, bucket: str, object_path: str, sha256: str) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO snapshot_metadata (snapshot_key, bucket, object, sha256)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
            """, (snapshot_key, bucket, object_path, sha256))
            snapshot_id = cur.fetchone()[0]
        conn.commit()
    return snapshot_id


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main(public: bool = False):
    if public:
        # Get latest internal snapshot (exclude public)
        with connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, snapshot_key
                FROM snapshot_metadata
                WHERE snapshot_key <> %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (f"{SNAP_VERSION}_public",)
            )
            row = cur.fetchone()
            if not row:
                raise SystemExit("no snapshot found")
            snapshot_id, snapshot_key = row

        snap = build_public_snapshot(snapshot_id, snapshot_key)
        prefix = f"{SNAP_VERSION}_public/_public"
        snapshot_key_for_db = f"{SNAP_VERSION}_public"
    else:
        snap = build_snapshot()
        prefix = SNAP_VERSION

    res = upload_snapshot(snap, prefix=prefix)

    # For public snapshots, also upload a stable latest.json
    if public:
        m = minio_client()
        latest_info = {
            "object": res["object"],
            "sha256": res["sha256"],
            "created_at": snap["meta"]["generated_at_utc"],
            "count": snap["meta"]["count"]  # Use the actual count from the snapshot being created
        }
        latest_payload = json.dumps(latest_info, ensure_ascii=False, indent=2, default=_json_default).encode("utf-8")
        put_bytes(
            m,
            SNAP_BUCKET,
            f"{SNAP_VERSION}_public/_public/latest.json",
            latest_payload,
            content_type="application/json",
        )

    snapshot_id = save_snapshot_metadata(
        snapshot_key=snapshot_key_for_db if public else prefix,
        bucket=res["bucket"],
        object_path=res["object"],
        sha256=res["sha256"],
    )

    print("[snapshot]", res)
    print(f"[snapshot] saved to postgres (id={snapshot_id})")


if __name__ == "__main__":
    main()