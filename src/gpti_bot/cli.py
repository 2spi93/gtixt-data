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
  access-check [limit]        - verify access to firm sites, aggregators, and web search results
  web-search <query> [n]      - test multi-engine web search (DuckDuckGo, Qwant, Yahoo)
  crawl [limit]               - crawl firms (candidate+watchlist), store raw+evidence, extract rules/pricing
    crawl-firm <firm_id>        - crawl a single firm by id
    extract-evidence-firm <firm_id> - force LLM extraction from stored evidence for a firm
    auto-enrich [limit]         - run multi-step enrichment pipeline for many firms
    auto-enrich-firm <firm_id>  - run multi-step enrichment pipeline for a single firm
    export-snapshot [--public]  - build and upload institutional snapshot to MinIO (public = Oversight Gate gated)
  score-snapshot              - compute weighted scores for latest snapshot
    verify-snapshot             - run institutional verification (Oversight Gate) on latest snapshot
    run-agents                  - execute RVI/REM/SSS agents and store evidence
    adaptive-enrichment [limit] - adaptive agent to enrich rules/pricing data
    adaptive-enrichment-firm <firm_id> - adaptive enrichment for a single firm
    proxy-enrichment [limit]    - proxy enrichment for missing firm metadata
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
    # access-check
    # -----------------------------------------------------
    if cmd == "access-check":
        limit = int(args[1]) if len(args) > 1 else 20
        from gpti_bot.health.access_check import run_access_check

        result = run_access_check(limit=limit)
        print(f"[access-check] {result}")
        return 1 if result.get("status") == "failed" else 0

    # -----------------------------------------------------
    # crawl
    # -----------------------------------------------------
    if cmd == "crawl":
        limit = int(args[1]) if len(args) > 1 else 20
        crawl_once(limit=limit)
        print(f"[crawl] done (limit={limit})")
        return 0

    if cmd == "crawl-firm":
        if len(args) < 2:
            print("Missing firm_id", file=sys.stderr)
            return 2
        firm_id = args[1]
        from gpti_bot.crawl import crawl_firm_by_id

        ok = crawl_firm_by_id(firm_id)
        if not ok:
            print(f"[crawl-firm] not found: {firm_id}")
            return 1
        print(f"[crawl-firm] done (firm_id={firm_id})")
        return 0

    if cmd == "extract-evidence-firm":
        if len(args) < 2:
            print("Missing firm_id", file=sys.stderr)
            return 2
        firm_id = args[1]
        from gpti_bot.extract_from_evidence import run_extract_from_evidence_for_firm

        result = run_extract_from_evidence_for_firm(firm_id)
        print(f"[extract-evidence] {result}")
        return 0

    if cmd == "auto-enrich":
        limit = int(args[1]) if len(args) > 1 else 20
        from gpti_bot.auto_enrich import run_auto_enrich

        result = run_auto_enrich(limit=limit)
        print(f"[auto-enrich] {result}")
        return 0

    if cmd == "auto-enrich-firm":
        if len(args) < 2:
            print("Missing firm_id", file=sys.stderr)
            return 2
        firm_id = args[1]
        from gpti_bot.auto_enrich import run_auto_enrich_for_firm

        result = run_auto_enrich_for_firm(firm_id)
        print(f"[auto-enrich] {result}")
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
    # adaptive enrichment agent
    # -----------------------------------------------------
    if cmd == "adaptive-enrichment":
        limit = int(args[1]) if len(args) > 1 else 60
        from gpti_bot.agents.adaptive_enrichment_agent import run_targeted_enrichment

        result = run_targeted_enrichment(limit=limit)
        print(f"[adaptive-enrichment] {result}")
        return 0

    if cmd == "adaptive-enrichment-firm":
        if len(args) < 2:
            print("Missing firm_id", file=sys.stderr)
            return 2
        firm_id = args[1]
        from gpti_bot.agents.adaptive_enrichment_agent import run_targeted_enrichment_for_firm

        result = run_targeted_enrichment_for_firm(firm_id)
        print(f"[adaptive-enrichment] {result}")
        return 0

    # -----------------------------------------------------
    # proxy enrichment
    # -----------------------------------------------------
    if cmd == "proxy-enrichment":
        limit = int(args[1]) if len(args) > 1 else None
        from gpti_bot.proxy_enrichment import run_proxy_enrichment

        result = run_proxy_enrichment(limit=limit)
        print(f"[proxy-enrichment] {result}")
        return 0

    # -----------------------------------------------------
    # web search test
    # -----------------------------------------------------
    if cmd == "web-search":
        if len(args) < 2:
            print("Usage: web-search <query> [max_results]", file=sys.stderr)
            return 2
        query = args[1]
        max_results = int(args[2]) if len(args) > 2 else 10
        
        from gpti_bot.discovery.web_search import web_search
        
        results = web_search(query, max_results=max_results)
        print(f"\n[web-search] Query: '{query}' ({len(results)} results)")
        print("-" * 80)
        for i, r in enumerate(results, 1):
            print(f"\n{i}. {r['title']} [{r['relevance']:.2f}]")
            print(f"   URL: {r['url']}")
            print(f"   Source: {r['source']}")
            print(f"   Snippet: {r['snippet'][:100]}...")
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