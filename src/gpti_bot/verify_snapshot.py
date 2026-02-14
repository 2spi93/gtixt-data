from __future__ import annotations

import json
from typing import Any

from .db import connect
from .agents.gate_agent_c import apply_agent_c_gate


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main() -> None:
    # Get latest snapshot ID
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id
            FROM snapshot_metadata
            WHERE snapshot_key <> %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            ("universe_v0.1_public",)
        )
        row = cur.fetchone()
        if not row:
            raise SystemExit("no snapshot found")

        snapshot_id = row[0]

    # Apply Oversight Gate
    report = apply_agent_c_gate(snapshot_id)

    # Also insert into old snapshot_audit for compatibility
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO snapshot_audit (snapshot_id, key, value)
            VALUES (%s, %s, %s)
            """,
            (
                snapshot_id,
                "agent_c_gate",
                json.dumps(report),
            ),
        )
        conn.commit()

    print(
        f"[agent-c] snapshot_id={report['snapshot_id']} "
        f"key={report['snapshot_key']} "
        f"total={report['total_firms']} "
        f"pass={report['pass_count']} "
        f"review={report['review_count']} "
        f"pass_rate={report['pass_rate']:.1%}"
    )


if __name__ == "__main__":
    main()