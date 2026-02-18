#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import os
import json
import signal
from typing import List

from gpti_bot.auto_enrich import run_auto_enrich_for_firm, _firm_has_data
from gpti_bot.db import connect
from gpti_bot.crawl import fetch_external_evidence
from gpti_bot.external_sources import rank_candidates_diverse

FIRM_SEED_PATH = os.getenv(
    "GPTI_FIRM_SEED_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "seeds", "firm_url_seeds.json")),
)


class FirmTimeoutError(TimeoutError):
    pass


def _load_firm_seed_urls() -> dict:
    try:
        with open(FIRM_SEED_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _fetch_firm_info(conn, firm_id: str) -> dict:
    sql = """
    SELECT firm_id, brand_name, website_root
    FROM firms
    WHERE firm_id = %s
    LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (firm_id,))
        row = cur.fetchone()
    if not row:
        return {}
    return {
        "firm_id": row[0],
        "brand_name": row[1],
        "website_root": row[2],
    }


def _external_urls_for_firm(firm_id: str) -> list[str]:
    data = _load_firm_seed_urls()
    entry = data.get((firm_id or "").lower())
    if not isinstance(entry, dict):
        return []
    urls = entry.get("external") or []
    if not isinstance(urls, list):
        return []
    return [u for u in urls if isinstance(u, str) and u.strip()]


def _run_with_timeout(seconds: int, func, *args, **kwargs):
    def handler(_signum, _frame):
        raise FirmTimeoutError("firm_timeout")

    previous = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        return func(*args, **kwargs)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _latest_missing_csv(tmp_dir: str) -> str | None:
    candidates = glob.glob(os.path.join(tmp_dir, "missing_fields_*.csv"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def _load_firm_ids(path: str, limit: int | None) -> List[str]:
    firm_ids: List[str] = []
    seen: set[str] = set()
    with open(path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            firm_id = (row.get("firm_id") or "").strip()
            if not firm_id:
                continue
            if firm_id in seen:
                continue
            seen.add(firm_id)
            firm_ids.append(firm_id)
            if limit is not None and len(firm_ids) >= limit:
                break
    return firm_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-enrich only firms with missing fields.")
    parser.add_argument("--tmp-dir", default="/opt/gpti/tmp", help="Directory with missing_fields_*.csv")
    parser.add_argument("--limit", type=int, default=None, help="Max firms to process")
    parser.add_argument("--resume", action="store_true", help="Skip firms that already have usable data")
    args = parser.parse_args()

    latest = _latest_missing_csv(args.tmp_dir)
    if not latest:
        print("[auto-enrich-missing] no missing_fields CSV found")
        return 1

    firm_ids = _load_firm_ids(latest, args.limit)
    if not firm_ids:
        print("[auto-enrich-missing] no firm ids found in CSV")
        return 1

    processed = 0
    skipped = 0
    with_data = 0
    errors = 0
    timeout_s = int(os.getenv("GPTI_FIRM_TIMEOUT_S", "240"))
    external_limit = int(os.getenv("GPTI_EXTERNAL_MAX_URLS", "10"))

    with connect() as conn:
        for firm_id in firm_ids:
            if args.resume and _firm_has_data(conn, firm_id):
                skipped += 1
                continue
            try:
                result = _run_with_timeout(timeout_s, run_auto_enrich_for_firm, firm_id)
                processed += 1
                if result.get("has_data"):
                    with_data += 1
                else:
                    external_urls = _external_urls_for_firm(firm_id)
                    firm_info = _fetch_firm_info(conn, firm_id)
                    ranked = rank_candidates_diverse(
                        firm_info.get("brand_name"),
                        firm_info.get("firm_id"),
                        firm_info.get("website_root"),
                        limit=external_limit,
                        per_slug=2,
                    )
                    all_external = list(dict.fromkeys(external_urls + ranked))
                    if all_external:
                        fetch_external_evidence(firm_id, all_external)
                        result = _run_with_timeout(timeout_s, run_auto_enrich_for_firm, firm_id)
                        if result.get("has_data"):
                            with_data += 1
            except FirmTimeoutError:
                errors += 1
                continue
            except Exception:
                errors += 1
                continue

    print(
        f"[auto-enrich-missing] processed={processed} skipped={skipped} with_data={with_data} errors={errors} "
        f"source={os.path.basename(latest)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
