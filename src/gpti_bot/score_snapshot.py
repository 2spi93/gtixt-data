from __future__ import annotations

import json
from typing import Any

from .db import connect
from .minio import client as minio_client, get_bytes
from .scoring.score_v1 import score_snapshot_v1

SNAP_BUCKET = "gpti-snapshots"


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main() -> None:
    # Load latest snapshot
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id
            FROM snapshot_metadata
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            raise SystemExit("no snapshot found")

        snapshot_id = row[0]

    # Score using v1.0
    summary = score_snapshot_v1(snapshot_id)
    print(f"[score] snapshot_id={summary['snapshot_id']} firms_scored={summary['firms_scored']} avg_score={summary['avg_score']}")


if __name__ == "__main__":
    main()