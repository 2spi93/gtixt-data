"""
Prefect flow to healthcheck Ollama and optionally restart it.
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import Dict

import requests
from prefect import flow, task, get_run_logger


@task(name="ping_ollama")
def ping_ollama(timeout_s: int = 8) -> None:
    base = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11435").rstrip("/")
    resp = requests.get(f"{base}/api/tags", timeout=timeout_s)
    resp.raise_for_status()


@task(name="restart_ollama")
def restart_ollama() -> bool:
    cmd = os.getenv("OLLAMA_RESTART_CMD", "").strip()
    if not cmd:
        return False

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"restart failed: {result.stderr.strip()}")
    return True


@task(name="send_slack")
def send_slack(message: str) -> None:
    url = os.getenv("SLACK_VALIDATION_WEBHOOK", "").strip()
    if not url:
        return
    requests.post(url, json={"text": message}, timeout=10)


@flow(name="healthcheck_ollama_flow", log_prints=True)
def healthcheck_ollama_flow() -> Dict[str, str | bool | int]:
    logger = get_run_logger()

    if os.getenv("OLLAMA_REQUIRED", "0") != "1":
        logger.warning("Ollama healthcheck skipped (OLLAMA_REQUIRED != 1)")
        return {"status": "skipped", "attempts": 0, "restarted": False}

    for attempt in range(1, 3):
        try:
            ping_ollama()
            logger.info("Ollama OK")
            return {"status": "ok", "attempts": attempt, "restarted": False}
        except Exception as exc:
            logger.warning(f"Ollama ping failed (attempt {attempt}/2): {exc}")
            time.sleep(4)

    restarted = False
    try:
        restarted = restart_ollama()
        if restarted:
            logger.warning("Ollama restart command executed")
            time.sleep(6)
    except Exception as exc:
        logger.error(f"Ollama restart failed: {exc}")

    for attempt in range(1, 3):
        try:
            ping_ollama()
            msg = "✅ Ollama recovered after restart" if restarted else "✅ Ollama recovered"
            send_slack(msg)
            return {"status": "ok", "attempts": attempt + 2, "restarted": restarted}
        except Exception as exc:
            logger.warning(f"Ollama ping failed after restart (attempt {attempt}/2): {exc}")
            time.sleep(4)

    send_slack("❌ Ollama healthcheck failed after restart attempts")
    raise RuntimeError("Ollama healthcheck failed")


if __name__ == "__main__":
    healthcheck_ollama_flow()
