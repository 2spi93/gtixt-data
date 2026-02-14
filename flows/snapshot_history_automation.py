"""
Snapshot History Automation Flow
Runs automatically after each snapshot publication
Captures and maintains historical score data in firm_snapshots table
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List
import json
import hashlib

try:
    from prefect import flow, task, get_run_logger
    from prefect.tasks.shell import shell_run_command
except ImportError:
    # Fallback for non-Prefect environments
    def flow(*args, **kwargs):
        def decorator(f):
            return f
        return decorator

    def task(*args, **kwargs):
        def decorator(f):
            return f
        return decorator

    def get_run_logger():
        class Logger:
            def info(self, msg):
                print(f"[INFO] {msg}")
            def error(self, msg):
                print(f"[ERROR] {msg}")
            def debug(self, msg):
                print(f"[DEBUG] {msg}")
        return Logger()


from gpti_bot.db import fetchall, execute, fetchone
from gpti_bot.snapshots.snapshot import make_snapshot
from gpti_bot.agents.snapshot_history_agent import get_snapshot_history_agent


@task(name="load_latest_snapshot", retries=2)
def load_latest_snapshot(model_type: str = "ALL") -> Dict[str, Any]:
    """Load the latest published snapshot"""
    logger = get_run_logger()
    
    try:
        # In production, this would load from MinIO
        # For now, we'll fetch from the local test snapshot
        import os
        import path as pathlib
        
        snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "../../gpti-site/data/test-snapshot.json"
        )
        
        if os.path.exists(snapshot_path):
            with open(snapshot_path, 'r') as f:
                data = json.load(f)
                logger.info(f"Loaded snapshot with {len(data.get('records', []))} firms")
                return {
                    "snapshot_id": f"{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}_{model_type.lower()}",
                    "records": data.get("records", []),
                    "timestamp": datetime.utcnow().isoformat(),
                }
        else:
            logger.error(f"Snapshot file not found: {snapshot_path}")
            return {"snapshot_id": "", "records": []}
            
    except Exception as e:
        logger.error(f"Error loading snapshot: {e}")
        raise


@task(name="compute_snapshot_hash")
def compute_snapshot_hash(data: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of snapshot data"""
    content = json.dumps(data.get("records", []), sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


@task(name="capture_firm_snapshots")
def capture_firm_snapshots(
    snapshot_data: Dict[str, Any],
    snapshot_hash: str
) -> int:
    """Capture firm snapshots to history table"""
    logger = get_run_logger()
    
    try:
        agent = get_snapshot_history_agent()
        count = agent.capture_snapshot(
            firms=snapshot_data.get("records", []),
            snapshot_id=snapshot_data.get("snapshot_id", ""),
            snapshot_hash=snapshot_hash,
        )
        logger.info(f"Captured {count} firm snapshots")
        return count
    except Exception as e:
        logger.error(f"Error capturing snapshots: {e}")
        raise


@task(name="verify_history_integrity")
def verify_history_integrity(firm_count: int) -> bool:
    """Verify that snapshots were properly captured"""
    logger = get_run_logger()
    
    try:
        # Check that records were inserted
        result = fetchone(
            "SELECT COUNT(*) FROM firm_snapshots WHERE created_at >= NOW() - INTERVAL '1 hour'"
        )
        
        if result and result[0] > 0:
            logger.info(f"Verified {result[0]} recent snapshot records in database")
            return True
        else:
            logger.error("No recent snapshot records found in database")
            return False
    except Exception as e:
        logger.error(f"Error verifying history: {e}")
        return False


@task(name="cleanup_old_snapshots")
def cleanup_old_snapshots(retention_days: int = 365) -> int:
    """Remove snapshots older than retention period"""
    logger = get_run_logger()
    
    try:
        # Delete snapshots older than retention period
        result = execute(
            f"""
            DELETE FROM firm_snapshots 
            WHERE created_at < NOW() - INTERVAL '{retention_days} days'
            RETURNING id
            """
        )
        
        logger.info(f"Cleaned up snapshots older than {retention_days} days")
        return 0  # Success
    except Exception as e:
        logger.error(f"Error cleaning up old snapshots: {e}")
        return -1


@task(name="generate_trajectory_report")
def generate_trajectory_report() -> Dict[str, Any]:
    """Generate trajectory analysis report"""
    logger = get_run_logger()
    
    try:
        # Get firms with trajectory data
        firms_with_history = fetchall(
            """
            SELECT DISTINCT firm_id, firm_name, COUNT(*) as snapshot_count
            FROM firm_snapshots
            WHERE captured_at >= NOW() - INTERVAL '90 days'
            GROUP BY firm_id, firm_name
            HAVING COUNT(*) >= 2
            ORDER BY snapshot_count DESC
            LIMIT 20
            """
        )
        
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "firms_with_trajectory": len(firms_with_history),
            "firms": [
                {
                    "firm_id": row[0],
                    "firm_name": row[1],
                    "snapshot_count": row[2],
                }
                for row in firms_with_history
            ],
        }
        
        logger.info(f"Generated trajectory report: {len(firms_with_history)} firms with history")
        return report
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return {}


@flow(name="snapshot_history_pipeline")
def snapshot_history_pipeline(model_type: str = "ALL"):
    """
    Main automation flow - runs after snapshot publication
    
    Steps:
    1. Load latest snapshot
    2. Compute snapshot hash
    3. Capture firm snapshots to database
    4. Verify integrity
    5. Cleanup old records
    6. Generate trajectory report
    """
    logger = get_run_logger()
    logger.info(f"Starting snapshot history pipeline for {model_type}")
    
    # Load snapshot
    snapshot_data = load_latest_snapshot(model_type)
    
    if not snapshot_data.get("records"):
        logger.error("No snapshot data available")
        return
    
    # Compute hash
    snapshot_hash = compute_snapshot_hash(snapshot_data)
    
    # Capture snapshots
    firm_count = capture_firm_snapshots(snapshot_data, snapshot_hash)
    
    # Verify integrity
    is_valid = verify_history_integrity(firm_count)
    
    if not is_valid:
        logger.error("History integrity check failed")
        return
    
    # Cleanup old data
    cleanup_old_snapshots(retention_days=365)
    
    # Generate report
    report = generate_trajectory_report()
    
    logger.info(f"Snapshot history pipeline completed successfully")
    logger.info(f"Report: {json.dumps(report, indent=2)}")


@flow(name="hourly_snapshot_monitor")
def hourly_snapshot_monitor():
    """
    Lightweight flow that runs hourly
    Checks if new snapshots are available and processes them
    """
    logger = get_run_logger()
    logger.info("Running hourly snapshot monitor")
    
    try:
        # Check if new snapshot was published in last hour
        result = fetchone(
            """
            SELECT COUNT(DISTINCT snapshot_id)
            FROM firm_snapshots
            WHERE created_at >= NOW() - INTERVAL '1 hour'
            """
        )
        
        if result and result[0] > 0:
            logger.info(f"Detected {result[0]} new snapshots in last hour")
            # Run full pipeline
            snapshot_history_pipeline()
        else:
            logger.info("No new snapshots detected")
            
    except Exception as e:
        logger.error(f"Error in hourly monitor: {e}")


if __name__ == "__main__":
    # Run pipeline directly
    snapshot_history_pipeline()
