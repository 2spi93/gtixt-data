from __future__ import annotations

import re
from typing import Any, Dict, Iterable

from .db import connect


def _infer_jurisdiction_from_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        url = value if value.startswith("http") else f"https://{value}"
        host = url.split("//", 1)[-1].split("/", 1)[0]
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


def _infer_jurisdiction_tier(jurisdiction: str | None) -> str | None:
    if not jurisdiction:
        return None
    value = jurisdiction.lower()
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


def _unwrap_datapoint_value(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        if isinstance(value.get("rules"), dict):
            return value.get("rules", {})
        if isinstance(value.get("value"), dict):
            return value.get("value", {})
        return value
    return {}


def _join_text(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("_audit", "source_urls"):
                continue
            parts.append(_join_text(v))
    elif isinstance(value, list):
        for item in value:
            parts.append(_join_text(item))
    elif value not in (None, ""):
        parts.append(str(value))
    return " ".join([p for p in parts if p]).strip()


def _extract_year(text: str) -> int | None:
    for match in re.findall(r"\b(19[5-9]\d|20[0-2]\d)\b", text):
        year = int(match)
        if 1990 <= year <= 2026:
            return year
    return None


def _detect_rule_change_frequency(text: str) -> str | None:
    lowered = text.lower()
    if any(token in lowered for token in ["daily", "every day"]):
        return "daily"
    if "weekly" in lowered or "every week" in lowered:
        return "weekly"
    if "monthly" in lowered or "every month" in lowered:
        return "monthly"
    if "quarter" in lowered or "quarterly" in lowered:
        return "quarterly"
    if "year" in lowered or "annually" in lowered:
        return "yearly"
    return None


def _merge_value(existing: Any, candidate: Any) -> Any:
    if existing not in (None, "", [], {}):
        return existing
    return candidate


def _fetch_latest_datapoints(conn, firm_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    firm_ids = list(firm_ids)
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
    results: Dict[str, Dict[str, Any]] = {}
    for firm_id, key, value in rows:
        results.setdefault(firm_id, {})[key] = value
    return results


def run_proxy_enrichment(limit: int | None = None) -> Dict[str, int]:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS firm_enrichment (
                firm_id TEXT PRIMARY KEY,
                founded_year INTEGER,
                founded TEXT,
                headquarters TEXT,
                jurisdiction_tier TEXT,
                rule_changes_frequency TEXT,
                historical_consistency TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        conn.commit()

        cur.execute("SELECT firm_id, website_root, jurisdiction, founded_year FROM firms ORDER BY firm_id")
        rows = cur.fetchall()
        if limit:
            rows = rows[: int(limit)]

        datapoints = _fetch_latest_datapoints(conn, [row[0] for row in rows])

        updated = 0
        processed = 0

        for firm_id, website_root, jurisdiction, founded_year in rows:
            processed += 1
            firm_data = datapoints.get(firm_id, {})
            rules_value = firm_data.get("rules_extracted_v0") or firm_data.get("rules_extracted_from_home_v0")
            pricing_value = firm_data.get("pricing_extracted_v0") or firm_data.get("pricing_extracted_from_home_v0")
            rules_data = _unwrap_datapoint_value(rules_value)
            pricing_data = _unwrap_datapoint_value(pricing_value)

            inferred_jurisdiction = jurisdiction or _infer_jurisdiction_from_url(website_root)
            headquarters = inferred_jurisdiction if inferred_jurisdiction and "global" not in inferred_jurisdiction.lower() else None
            jurisdiction_tier = _infer_jurisdiction_tier(inferred_jurisdiction)

            rule_changes_frequency = rules_data.get("rule_changes_frequency") or rules_data.get("rule_change_frequency")
            if not rule_changes_frequency:
                rule_changes_frequency = _detect_rule_change_frequency(_join_text(rules_data))

            merged_text = " ".join(
                [
                    _join_text(rules_data),
                    _join_text(pricing_data),
                ]
            ).strip()
            inferred_year = _extract_year(merged_text)
            resolved_year = founded_year or inferred_year

            cur.execute(
                """
                SELECT founded_year, founded, headquarters, jurisdiction_tier, rule_changes_frequency, historical_consistency
                FROM firm_enrichment
                WHERE firm_id = %s
                """,
                (firm_id,),
            )
            existing = cur.fetchone()
            if existing:
                existing_year, existing_founded, existing_hq, existing_tier, existing_rules, existing_hist = existing
            else:
                existing_year = existing_founded = existing_hq = existing_tier = existing_rules = existing_hist = None

            new_year = _merge_value(existing_year, resolved_year)
            new_founded = _merge_value(existing_founded, None)
            new_hq = _merge_value(existing_hq, headquarters)
            new_tier = _merge_value(existing_tier, jurisdiction_tier)
            new_rules = _merge_value(existing_rules, rule_changes_frequency)
            new_hist = _merge_value(existing_hist, None)

            if (new_year, new_founded, new_hq, new_tier, new_rules, new_hist) == (
                existing_year,
                existing_founded,
                existing_hq,
                existing_tier,
                existing_rules,
                existing_hist,
            ):
                continue

            cur.execute(
                """
                INSERT INTO firm_enrichment (
                    firm_id,
                    founded_year,
                    founded,
                    headquarters,
                    jurisdiction_tier,
                    rule_changes_frequency,
                    historical_consistency,
                    updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s, NOW())
                ON CONFLICT (firm_id) DO UPDATE SET
                    founded_year = EXCLUDED.founded_year,
                    founded = EXCLUDED.founded,
                    headquarters = EXCLUDED.headquarters,
                    jurisdiction_tier = EXCLUDED.jurisdiction_tier,
                    rule_changes_frequency = EXCLUDED.rule_changes_frequency,
                    historical_consistency = EXCLUDED.historical_consistency,
                    updated_at = NOW()
                """,
                (
                    firm_id,
                    new_year,
                    new_founded,
                    new_hq,
                    new_tier,
                    new_rules,
                    new_hist,
                ),
            )
            updated += 1

        conn.commit()

    return {"processed": processed, "updated": updated}
