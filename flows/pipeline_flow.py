"""
Prefect flow for automated GPTI data pipeline
Run every 6 hours: crawl → score → verify → export-public
"""

from prefect import flow, task
from datetime import datetime
import subprocess
import os

from flows.healthcheck_ollama_flow import healthcheck_ollama_flow

@task
def run_discover():
    """Run the discovery phase"""
    result = subprocess.run([
        "docker", "compose", "exec", "-T", "bot",
        "python", "-m", "gpti_bot.cli", "discover"
    ], cwd="/opt/gpti/gpti-data-bot/infra", capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Discovery failed: {result.stderr}")
    return result.stdout

@task
def run_score_snapshot():
    """Run scoring on latest snapshot"""
    result = subprocess.run([
        "docker", "compose", "exec", "-T", "bot",
        "python", "-m", "gpti_bot.cli", "score-snapshot"
    ], cwd="/opt/gpti/gpti-data-bot/infra", capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Score snapshot failed: {result.stderr}")
    return result.stdout

@task
def run_verify_snapshot():
    """Run Oversight Gate quality verification"""
    result = subprocess.run([
        "docker", "compose", "exec", "-T", "bot",
        "python", "-m", "gpti_bot.cli", "verify-snapshot"
    ], cwd="/opt/gpti/gpti-data-bot/infra", capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Verify snapshot failed: {result.stderr}")
    return result.stdout

@task
def run_export_public():
    """Export public snapshot with quality filtering"""
    result = subprocess.run([
        "docker", "compose", "exec", "-T", "bot",
        "python", "-m", "gpti_bot.cli", "export-snapshot", "--public"
    ], cwd="/opt/gpti/gpti-data-bot/infra", capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Export public failed: {result.stderr}")
    return result.stdout

@flow(name="GPTI Data Pipeline", log_prints=True)
def gpti_data_pipeline():
    """Complete GPTI data pipeline with quality gates"""
    print(f"Starting GPTI pipeline at {datetime.now()}")

    # Ensure Ollama is healthy before pipeline
    healthcheck_ollama_flow()

    # Sequential execution to ensure data consistency
    discover_result = run_discover()
    print("✓ Discovery completed")

    score_result = run_score_snapshot()
    print("✓ Scoring completed")

    verify_result = run_verify_snapshot()
    print("✓ Quality verification completed")

    export_result = run_export_public()
    print("✓ Public export completed")

    print(f"Pipeline completed successfully at {datetime.now()}")
    return {
        "discover": discover_result,
        "score": score_result,
        "verify": verify_result,
        "export": export_result
    }

if __name__ == "__main__":
    # For local testing
    result = gpti_data_pipeline()
    print("Pipeline result:", result)