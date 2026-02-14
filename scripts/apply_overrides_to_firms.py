#!/usr/bin/env python3
"""Apply overrides into firm_enrichment table."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import psycopg

DEFAULT_OVERRIDES_DIR = "/opt/gpti/gpti-site/data"


def _read_overrides(path: str) -> dict[str, Any]:
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


def main() -> int:
    overrides_dir = os.getenv("GPTI_OVERRIDES_DIR", DEFAULT_OVERRIDES_DIR)
    auto_path = os.path.join(overrides_dir, "firm-overrides.auto.json")
    manual_path = os.path.join(overrides_dir, "firm-overrides.json")

    overrides = {**_read_overrides(auto_path), **_read_overrides(manual_path)}
    if not overrides:
        print("No overrides found.")
        return 0

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is required")

    conn = psycopg.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    updated = 0
    for firm_id, data in overrides.items():
        if not isinstance(data, dict):
            continue
        founded_year = data.get("founded_year")
        founded = data.get("founded")
        headquarters = data.get("headquarters")
        jurisdiction_tier = data.get("jurisdiction_tier")
        rule_changes_frequency = data.get("rule_changes_frequency")
        historical_consistency = data.get("historical_consistency")
        sources = data.get("_sources")
        if all(
            value is None
            for value in (
                founded_year,
                founded,
                headquarters,
                jurisdiction_tier,
                rule_changes_frequency,
                historical_consistency,
            )
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
              sources,
              updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (firm_id) DO UPDATE SET
              founded_year = COALESCE(EXCLUDED.founded_year, firm_enrichment.founded_year),
              founded = COALESCE(EXCLUDED.founded, firm_enrichment.founded),
              headquarters = COALESCE(EXCLUDED.headquarters, firm_enrichment.headquarters),
              jurisdiction_tier = COALESCE(EXCLUDED.jurisdiction_tier, firm_enrichment.jurisdiction_tier),
              rule_changes_frequency = COALESCE(EXCLUDED.rule_changes_frequency, firm_enrichment.rule_changes_frequency),
              historical_consistency = COALESCE(EXCLUDED.historical_consistency, firm_enrichment.historical_consistency),
              sources = COALESCE(EXCLUDED.sources, firm_enrichment.sources),
              updated_at = NOW()
            """,
            (
                firm_id,
                founded_year,
                founded,
                headquarters,
                jurisdiction_tier,
                rule_changes_frequency,
                historical_consistency,
                json.dumps(sources) if isinstance(sources, dict) else None,
            ),
        )
        if cur.rowcount:
            updated += cur.rowcount

    print(f"Updated {updated} firm rows.")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
