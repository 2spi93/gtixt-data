"""
Prefect flow for GTIXT validation & monitoring
Run every 6 hours after pipeline_flow completes
Implements 6 validation tests + alerting per IOSCO standards
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

sys.path.insert(0, '/opt/gpti/gpti-data-bot/src')

from prefect import flow, task
from gpti_bot.validation.db_utils import ValidationDB

logger = logging.getLogger(__name__)


def resolve_latest_snapshot_key() -> str:
    """Resolve snapshot_key from latest.json pointer."""
    pointer_url = os.environ.get(
        "VALIDATION_LATEST_POINTER_URL",
        "http://51.210.246.61:9000/gpti-snapshots/universe_v0.1_public/_public/latest.json"
    )
    resp = requests.get(pointer_url, timeout=10)
    resp.raise_for_status()
    payload = resp.json()

    snapshot_uri = payload.get("snapshot_uri") or payload.get("snapshotUrl") or ""
    if snapshot_uri:
        # Expected format: .../gpti-snapshots/{snapshot_key}/...
        parts = snapshot_uri.split("/gpti-snapshots/")
        if len(parts) > 1:
            return parts[1].split("/")[0]

    object_path = payload.get("object") or ""
    if object_path and "/" in object_path:
        return object_path.split("/")[0]

    snapshot_key = payload.get("snapshot_key") or payload.get("snapshotKey")
    if snapshot_key:
        return snapshot_key

    raise ValueError("Unable to resolve snapshot_key from latest.json")


@task(name="compute_coverage_metrics", retries=2)
def compute_coverage_metrics(snapshot_id: str) -> Dict:
    """Test 1: Coverage & Data Sufficiency"""
    logger.info(f"Computing coverage metrics for {snapshot_id}")
    try:
        metrics = ValidationDB.compute_coverage_metrics(snapshot_id)
        logger.info(f"Coverage: {metrics}")
        return metrics
    except Exception as e:
        logger.error(f"Coverage metrics failed: {e}", exc_info=True)
        raise


@task(name="compute_stability_metrics", retries=2)
def compute_stability_metrics(snapshot_id: str, prev_snapshot_id: Optional[str] = None) -> Dict:
    """Test 2: Stability & Turnover"""
    logger.info(f"Computing stability metrics for {snapshot_id}")
    try:
        metrics = ValidationDB.compute_stability_metrics(snapshot_id, prev_snapshot_id)
        logger.info(f"Stability: {metrics}")
        return metrics
    except Exception as e:
        logger.error(f"Stability metrics failed: {e}", exc_info=True)
        raise


@task(name="compute_ground_truth_validation", retries=2)
def compute_ground_truth_validation(snapshot_id: str) -> Dict:
    """Test 4: Ground-Truth Event Validation"""
    logger.info(f"Computing ground-truth validation for {snapshot_id}")
    try:
        metrics = ValidationDB.compute_ground_truth_validation(snapshot_id)
        logger.info(f"Ground-truth: {metrics}")
        return metrics
    except Exception as e:
        logger.error(f"Ground-truth validation failed: {e}", exc_info=True)
        raise


@task(name="compute_sensitivity_metrics", retries=2)
def compute_sensitivity_metrics(snapshot_id: str) -> Dict:
    """Test 3: Sensitivity & Stress Tests"""
    logger.info(f"Computing sensitivity metrics for {snapshot_id}")
    try:
        metrics = ValidationDB.compute_sensitivity_metrics(snapshot_id)
        logger.info(f"Sensitivity: {metrics}")
        return metrics
    except Exception as e:
        logger.error(f"Sensitivity metrics failed: {e}", exc_info=True)
        raise


@task(name="compute_calibration_bias_metrics", retries=2)
def compute_calibration_bias_metrics(snapshot_id: str) -> Dict:
    """Test 5: Calibration / Bias checks"""
    logger.info(f"Computing calibration/bias metrics for {snapshot_id}")
    try:
        metrics = ValidationDB.compute_calibration_bias_metrics(snapshot_id)
        logger.info(f"Calibration/Bias: {metrics}")
        return metrics
    except Exception as e:
        logger.error(f"Calibration/Bias metrics failed: {e}", exc_info=True)
        raise


@task(name="compute_auditability_metrics", retries=2)
def compute_auditability_metrics(snapshot_id: str) -> Dict:
    """Test 6: Auditability"""
    logger.info(f"Computing auditability metrics for {snapshot_id}")
    try:
        metrics = ValidationDB.compute_auditability_metrics(snapshot_id)
        logger.info(f"Auditability: {metrics}")
        return metrics
    except Exception as e:
        logger.error(f"Auditability metrics failed: {e}", exc_info=True)
        raise


@task(name="check_alerts")
def check_alerts(coverage: Dict, stability: Dict, ground_truth: Dict, sensitivity: Dict, calibration: Dict, auditability: Dict) -> List[Dict]:
    """Detect validation anomalies"""
    logger.info("Checking for validation anomalies")
    alerts = []

    if coverage.get("avg_na_rate", 0) > 25:
        alerts.append({
            "type": "NA_SPIKE", "severity": "warning",
            "message": f"NA rate {coverage['avg_na_rate']}% > 25%"
        })

    if coverage.get("coverage_percent", 100) < 70:
        alerts.append({
            "type": "COVERAGE_DROP", "severity": "critical",
            "message": f"Coverage {coverage['coverage_percent']}% < 70%"
        })

    if coverage.get("agent_c_pass_rate", 100) < 80:
        alerts.append({
            "type": "FAIL_RATE_UP", "severity": "warning",
            "message": f"Pass rate {coverage['agent_c_pass_rate']}% < 80%"
        })

    if stability.get("top_10_turnover", 0) > 5:
        alerts.append({
            "type": "TURNOVER_SPIKE", "severity": "warning",
            "message": f"Top 10 turnover {stability['top_10_turnover']} > 5"
        })

    if sensitivity.get("fallback_usage_percent", 0) > 35:
        alerts.append({
            "type": "FALLBACK_USAGE_HIGH", "severity": "warning",
            "message": f"Fallback usage {sensitivity['fallback_usage_percent']}% > 35%"
        })

    if sensitivity.get("stability_score", 100) < 70:
        alerts.append({
            "type": "STABILITY_SCORE_LOW", "severity": "warning",
            "message": f"Stability score {sensitivity['stability_score']} < 70"
        })

    if calibration.get("model_type_bias_score", 0) > 15:
        alerts.append({
            "type": "MODEL_TYPE_BIAS", "severity": "warning",
            "message": f"Model type bias {calibration['model_type_bias_score']} > 15"
        })

    if auditability.get("evidence_linkage_rate", 100) < 70:
        alerts.append({
            "type": "EVIDENCE_LINKAGE_LOW", "severity": "warning",
            "message": f"Evidence linkage {auditability['evidence_linkage_rate']}% < 70%"
        })

    logger.info(f"Generated {len(alerts)} alerts")
    return alerts


@task(name="send_alerts")
def send_alerts(alerts: List[Dict], snapshot_id: str):
    """Send Slack notifications"""
    if not alerts:
        logger.info("No alerts to send")
        return

    slack_url = os.environ.get("SLACK_VALIDATION_WEBHOOK")
    if not slack_url:
        logger.warning("SLACK_VALIDATION_WEBHOOK not configured")
        return

    try:
        import requests
        blocks = [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"🚨 *Validation Alerts* `{snapshot_id}`"}
        }]
        for alert in alerts:
            icon = "🔴" if alert["severity"] == "critical" else "🟡"
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"{icon} {alert['type']}: {alert['message']}"}
            })
        
        requests.post(slack_url, json={"blocks": blocks}, timeout=10)
        logger.info("Slack notification sent")
    except Exception as e:
        logger.error(f"Slack notification failed: {e}")


@task(name="send_summary")
def send_summary(snapshot_id: str, coverage: Dict, stability: Dict, ground_truth: Dict, sensitivity: Dict, calibration: Dict, auditability: Dict):
    """Send a validation summary to Slack."""
    slack_url = os.environ.get("SLACK_VALIDATION_WEBHOOK")
    if not slack_url:
        logger.warning("SLACK_VALIDATION_WEBHOOK not configured")
        return

    message = (
        "✅ Validation Summary\n"
        f"Snapshot: {snapshot_id}\n"
        f"Coverage: {coverage.get('coverage_percent', 0)}% | NA: {coverage.get('avg_na_rate', 0)}% | Pass: {coverage.get('agent_c_pass_rate', 0)}%\n"
        f"Stability: Δavg {stability.get('avg_score_change', 0)} | Top10 {stability.get('top_10_turnover', 0)} | Top20 {stability.get('top_20_turnover', 0)}\n"
        f"Sensitivity: mean {sensitivity.get('pillar_sensitivity_mean', 0)} | fallback {sensitivity.get('fallback_usage_percent', 0)}% | score {sensitivity.get('stability_score', 0)}\n"
        f"Calibration: skew {calibration.get('score_distribution_skew', 0)} | model bias {calibration.get('model_type_bias_score', 0)}\n"
        f"Auditability: evidence {auditability.get('evidence_linkage_rate', 0)}% | version {auditability.get('version_metadata', 'n/a')}\n"
        f"Ground-truth: events {ground_truth.get('events_in_period', 0)} | predicted {ground_truth.get('events_predicted', 0)} | precision {ground_truth.get('prediction_precision', 0)}%"
    )

    try:
        requests.post(slack_url, json={"text": message}, timeout=10)
        logger.info("Slack summary sent")
    except Exception as e:
        logger.error(f"Slack summary failed: {e}")


@task(name="store_metrics")
def store_metrics(snapshot_id: str, coverage: Dict, stability: Dict, ground_truth: Dict, sensitivity: Dict, calibration: Dict, auditability: Dict):
    """Store validation metrics in database"""
    logger.info(f"Storing metrics for {snapshot_id}")
    metrics = {
        "coverage": coverage,
        "stability": stability,
        "ground_truth": ground_truth,
        "sensitivity": sensitivity,
        "calibration": calibration,
        "auditability": auditability
    }
    
    if not ValidationDB.store_validation_metrics(snapshot_id, metrics):
        raise Exception("Failed to store validation metrics")


@flow(name="validation_flow", description="IOSCO-aligned 6-hour validation suite")
def validation_flow(snapshot_id: str):
    """Run validation after pipeline_flow completes"""
    if snapshot_id in ("latest", "latest.json", "public"):
        snapshot_id = resolve_latest_snapshot_key()

    logger.info(f"Starting validation_flow for {snapshot_id}")

    coverage = compute_coverage_metrics(snapshot_id)
    stability = compute_stability_metrics(snapshot_id)
    ground_truth = compute_ground_truth_validation(snapshot_id)
    sensitivity = compute_sensitivity_metrics(snapshot_id)
    calibration = compute_calibration_bias_metrics(snapshot_id)
    auditability = compute_auditability_metrics(snapshot_id)

    alerts = check_alerts(coverage, stability, ground_truth, sensitivity, calibration, auditability)
    send_alerts(alerts, snapshot_id)
    send_summary(snapshot_id, coverage, stability, ground_truth, sensitivity, calibration, auditability)
    store_metrics(snapshot_id, coverage, stability, ground_truth, sensitivity, calibration, auditability)

    logger.info(f"Completed validation_flow for {snapshot_id}")


if __name__ == "__main__":
    import sys
    snapshot_arg = sys.argv[1] if len(sys.argv) > 1 else "latest"
    validation_flow(snapshot_arg)
