#!/usr/bin/env python3
"""Export active GTIXT scoring spec to the site public directory."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict

import psycopg


def _build_db_url() -> str:
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url

    user = os.environ.get("POSTGRES_USER", "gpti")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "gpti")

    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return f"postgresql://{user}@{host}:{port}/{db}"


def _load_active_spec(conn: psycopg.Connection) -> Dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT version_key, data_dictionary, weights, hierarchy
            FROM score_version
            WHERE is_active = true
            LIMIT 1
            """
        )
        row = cur.fetchone()

    if not row:
        raise RuntimeError("No active scoring version found in score_version")

    version_key, data_dict, weights, hierarchy = row
    spec: Dict[str, Any] = dict(data_dict or {})
    spec["weights"] = weights or {}
    spec["hierarchy"] = hierarchy or {}
    spec["version_key"] = version_key
    return spec


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export active GTIXT scoring spec as JSON")
    parser.add_argument(
        "--output",
        default="/opt/gpti/gpti-site/public/spec/gpti_score_v1.json",
        help="Path to write spec JSON (default: site public/spec)",
    )
    args = parser.parse_args()

    db_url = _build_db_url()
    with psycopg.connect(db_url) as conn:
        spec = _load_active_spec(conn)

    output_path = Path(args.output)
    _write_json(output_path, spec)
    print(f"Exported scoring spec to {output_path}")


if __name__ == "__main__":
    main()
