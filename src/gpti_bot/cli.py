from __future__ import annotations

import sys
import os
import requests

from gpti_bot.discover import main as discover_main
from gpti_bot.crawl import crawl_once
from gpti_bot.export_snapshot import main as export_snapshot_main
from gpti_bot.score_snapshot import main as score_snapshot_main
from gpti_bot.verify_snapshot import main as verify_snapshot_main


# ---------------------------------------------------------
# Ollama connectivity check
# ---------------------------------------------------------

def _verify_ollama() -> int:
    base = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11435").rstrip("/")
    try:
        r = requests.get(base + "/api/tags", timeout=10)
        print("[ollama]", r.status_code, r.text[:400])
        return 0
    except Exception as e:
        print("[ollama] ERROR:", e)
        return 1


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

HELP_TEXT = """
GPTI Data Bot — Institutional CLI

Commands:
  discover [seed_path]        - upsert firms from seed JSON into Postgres
  verify-ollama               - check Ollama connectivity (/api/tags)
  crawl [limit]               - crawl firms (candidate+watchlist), store raw+evidence, extract rules/pricing
    export-snapshot [--public]  - build and upload institutional snapshot to MinIO (public = Oversight Gate gated)
  score-snapshot              - compute weighted scores for latest snapshot
    verify-snapshot             - run institutional verification (Oversight Gate) on latest snapshot
    run-agents                  - execute RVI/REM/SSS agents and store evidence
  help                        - show this help
"""


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("help", "-h", "--help"):
        print(HELP_TEXT)
        return 0

    cmd = args[0]

    # -----------------------------------------------------
    # discover
    # -----------------------------------------------------
    if cmd == "discover":
        seed_path = args[1] if len(args) > 1 else None
        return discover_main(seed_path)

    # -----------------------------------------------------
    # verify-ollama
    # -----------------------------------------------------
    if cmd == "verify-ollama":
        return _verify_ollama()

    # -----------------------------------------------------
    # crawl
    # -----------------------------------------------------
    if cmd == "crawl":
        limit = int(args[1]) if len(args) > 1 else 20
        crawl_once(limit=limit)
        print(f"[crawl] done (limit={limit})")
        return 0

    # -----------------------------------------------------
    # run agents (RVI/REM/SSS)
    # -----------------------------------------------------
    if cmd == "run-agents":
        import asyncio
        from gpti_bot.db import connect, fetch_firms
        from gpti_bot.agents.rvi_agent import RVIAgent
        from gpti_bot.agents.rem_agent import REMAgent
        from gpti_bot.agents.sss_agent import SSSAgent

        limit = int(os.getenv("GPTI_AGENT_LIMIT", "200"))
        with connect() as conn:
            firms = fetch_firms(conn, statuses=("candidate", "watchlist", "eligible"), limit=limit)

        async def run_all():
            rvi = RVIAgent()
            rem = REMAgent()
            sss = SSSAgent()
            await rvi.execute(firms)
            await rem.execute(firms)
            await sss.execute(firms)

        asyncio.run(run_all())
        print(f"[agents] completed RVI/REM/SSS for {len(firms)} firms")
        return 0

    # -----------------------------------------------------
    # export snapshot
    # -----------------------------------------------------
    if cmd == "export-snapshot":
        public = "--public" in args
        return export_snapshot_main(public=public)

    # -----------------------------------------------------
    # score snapshot
    # -----------------------------------------------------
    if cmd == "score-snapshot":
        return score_snapshot_main()

    # -----------------------------------------------------
    # verify snapshot
    # -----------------------------------------------------
    if cmd == "verify-snapshot":
        return verify_snapshot_main()

    # -----------------------------------------------------
    # unknown
    # -----------------------------------------------------
    print(f"Unknown command: {cmd}", file=sys.stderr)
    print(HELP_TEXT)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())