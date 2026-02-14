"""
Prefect flow: GTIXT production pipeline (6h)
Sequence: discover (optional) → crawl → export snapshot (internal) → score → verify → export snapshot (public) → validation → Slack summary
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from typing import Dict

import requests
from prefect import flow, task, get_run_logger

from flows.healthcheck_ollama_flow import healthcheck_ollama_flow
from flows.validation_flow import validation_flow


def _run_cli(*args: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "bot", "python", "-m", "gpti_bot.cli", *args],
        cwd="/opt/gpti/gpti-data-bot/infra",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {' '.join(args)}")
    return result.stdout.strip()


@task(name="discover")
def run_discover(seed_path: str | None = None) -> str:
    args = ["discover"] + ([seed_path] if seed_path else [])
    return _run_cli(*args)


@task(name="crawl")
def run_crawl(limit: int) -> str:
    return _run_cli("crawl", str(limit))


@task(name="run_agents")
def run_agents() -> str:
    return _run_cli("run-agents")


@task(name="export_snapshot_internal")
def run_export_internal() -> str:
    return _run_cli("export-snapshot")


@task(name="score_snapshot")
def run_score_snapshot() -> str:
    return _run_cli("score-snapshot")


@task(name="verify_snapshot")
def run_verify_snapshot() -> str:
    return _run_cli("verify-snapshot")


@task(name="export_snapshot_public")
def run_export_public() -> str:
    return _run_cli("export-snapshot", "--public")


@task(name="send_pipeline_summary")
def send_pipeline_summary(message: str) -> None:
    url = os.environ.get("SLACK_PIPELINE_WEBHOOK") or os.environ.get("SLACK_VALIDATION_WEBHOOK")
    if not url:
        return
    requests.post(url, json={"text": message}, timeout=10)


@flow(name="gtixt_production_pipeline", log_prints=True)
def production_pipeline() -> Dict[str, str]:
    logger = get_run_logger()

    crawl_limit = int(os.environ.get("CRAWL_LIMIT", "50"))
    discover_enabled = os.environ.get("DISCOVER_ENABLED", "false").lower() in ("1", "true", "yes")
    seed_path = os.environ.get("DISCOVER_SEED_PATH")

    logger.info(f"Starting GTIXT production pipeline at {datetime.now().isoformat()}")

    healthcheck_ollama_flow()

    if discover_enabled:
        logger.info("Running discover")
        run_discover(seed_path)

    logger.info("Running crawl")
    run_crawl(crawl_limit)

    logger.info("Running agents (RVI/REM/SSS)")
    run_agents()

    logger.info("Exporting internal snapshot")
    run_export_internal()

    logger.info("Scoring snapshot")
    run_score_snapshot()

    logger.info("Verifying snapshot (Integrity Gate)")
    run_verify_snapshot()

    logger.info("Exporting public snapshot")
    run_export_public()

    logger.info("Running validation flow")
    validation_flow("latest")

    summary = (
        "✅ GTIXT production pipeline completed\n"
        f"Time: {datetime.now().isoformat()}\n"
        f"Crawl limit: {crawl_limit}\n"
        f"Discover: {'on' if discover_enabled else 'off'}"
    )
    send_pipeline_summary(summary)

    return {
        "status": "ok",
        "crawl_limit": str(crawl_limit),
        "discover": "on" if discover_enabled else "off",
    }


if __name__ == "__main__":
    production_pipeline()
