from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass
from typing import Sequence, Iterable

import psycopg


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def get_database_url() -> str:
    url = _env("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set (expected: postgresql://user:pass@host:5432/db)"
        )
    return url


def connect(*, autocommit: bool = True) -> psycopg.Connection:
    """
    Create a psycopg3 connection from DATABASE_URL.
    autocommit=True ensures INSERT/UPDATE happen immediately.
    """
    conn = psycopg.connect(get_database_url())
    conn.autocommit = autocommit
    return conn


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """
    Convert text into a stable slug:
    - lowercase
    - replace spaces with hyphens
    - remove invalid chars
    - collapse multiple hyphens
    """
    text = text.strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-]+", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "unknown"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FirmRow:
    firm_id: str
    brand_name: str
    website_root: str
    model_type: str  # CFD_FX | FUTURES | HYBRID
    status: str      # candidate | eligible | watchlist | excluded
    jurisdiction: str | None = None
    jurisdiction_tier: str | None = None


# ---------------------------------------------------------------------------
# Firm operations
# ---------------------------------------------------------------------------

def upsert_firms(conn: psycopg.Connection, firms: Sequence[FirmRow]) -> int:
    """
    Insert/update firms in bulk.
    Ensures updated_at is refreshed on every update.
    """
    if not firms:
        return 0

    sql = """
    INSERT INTO firms (firm_id, brand_name, website_root, model_type, status, jurisdiction, jurisdiction_tier)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (firm_id) DO UPDATE SET
        brand_name        = EXCLUDED.brand_name,
        website_root      = EXCLUDED.website_root,
        model_type        = EXCLUDED.model_type,
        status            = EXCLUDED.status,
        jurisdiction      = COALESCE(EXCLUDED.jurisdiction, firms.jurisdiction),
        jurisdiction_tier = COALESCE(EXCLUDED.jurisdiction_tier, firms.jurisdiction_tier),
        updated_at        = now();
    """

    with conn.cursor() as cur:
        cur.executemany(
            sql,
            [
                (
                    f.firm_id,
                    f.brand_name,
                    f.website_root,
                    f.model_type,
                    f.status,
                    f.jurisdiction,
                    f.jurisdiction_tier,
                )
                for f in firms
            ],
        )

    return len(firms)


def fetch_firms(
    conn,
    *,
    statuses: Iterable[str] = ("candidate", "watchlist"),
    limit: int = 50
) -> list[dict]:
    """
    Fetch firms for crawling or verification.
    Only firms with a non-empty website_root are returned.
    """
    sql = """
    SELECT firm_id, brand_name, website_root, model_type, status
    FROM firms
    WHERE status = ANY(%s)
      AND coalesce(website_root, '') <> ''
    ORDER BY updated_at DESC
    LIMIT %s;
    """

    with conn.cursor() as cur:
        cur.execute(sql, (list(statuses), limit))
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Evidence + Datapoints
# ---------------------------------------------------------------------------

def insert_evidence(
    conn,
    *,
    firm_id: str,
    key: str,
    source_url: str,
    sha256: str,
    excerpt: str | None,
    raw_object_path: str | None
) -> None:
    """
    Insert evidence for a firm (HTML snapshot, excerpt, etc.).
    Evidence is deduplicated by (firm_id, key, sha256).
    """
    sql = """
    INSERT INTO evidence (firm_id, key, source_url, sha256, excerpt, raw_object_path)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (firm_id, key, sha256) DO NOTHING;
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (firm_id, key, source_url, sha256, excerpt, raw_object_path)
        )


def insert_datapoint(
    conn,
    *,
    firm_id: str,
    key: str,
    value_json: dict,
    value_text: str | None,
    source_url: str | None,
    evidence_hash: str | None
) -> None:
    """
    Insert a datapoint extracted by an agent.
    JSON is stored as JSONB.
    """
    sql = """
    INSERT INTO datapoints (firm_id, key, value_json, value_text, source_url, evidence_hash)
    VALUES (%s, %s, %s::jsonb, %s, %s, %s);
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                firm_id,
                key,
                json.dumps(value_json),
                value_text,
                source_url,
                evidence_hash,
            ),
        )