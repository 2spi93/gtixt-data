"""
Snapshot History Agent
Maintains firm_snapshots table with historical score data
Runs after each snapshot is published
"""

import json
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from gpti_bot.db import execute, fetchall, fetchone


@dataclass
class FirmSnapshot:
    """Represents a point-in-time firm snapshot"""
    firm_id: str
    firm_name: str
    score: float
    confidence: str
    snapshot_id: str
    percentile_overall: Optional[float] = None
    percentile_model: Optional[float] = None
    percentile_jurisdiction: Optional[float] = None
    pillar_scores: Optional[Dict[str, float]] = None
    metrics: Optional[Dict[str, Any]] = None
    status: str = "candidate"
    oversight_gate_verdict: Optional[str] = None
    audit_verdict: Optional[str] = None


class SnapshotHistoryAgent:
    """
    Maintains historical snapshots of firm scores
    - Captures scores from each published snapshot
    - Stores in firm_snapshots table
    - Enables historical tracking and trajectory analysis
    """

    def __init__(self):
        self.table_name = "firm_snapshots"

    def capture_snapshot(
        self, 
        firms: List[Dict[str, Any]], 
        snapshot_id: str,
        snapshot_hash: str
    ) -> int:
        """
        Capture firm scores from a snapshot publication
        
        Args:
            firms: List of firm records from snapshot
            snapshot_id: ID of the snapshot (e.g., '20260201T000000Z_all')
            snapshot_hash: SHA-256 hash of snapshot file
            
        Returns:
            Number of records inserted/updated
        """
        count = 0
        
        for firm in firms:
            try:
                # Extract firm data
                firm_id = firm.get("firm_id") or firm.get("id")
                firm_name = firm.get("firm_name") or firm.get("name")
                score = firm.get("score_0_100") or firm.get("score") or firm.get("integrity_score")
                
                if not firm_id or not firm_name or score is None:
                    continue
                
                # Normalize score
                score_normalized = score / 100 if score > 1 else score
                
                # Extract confidence
                confidence = firm.get("confidence", "medium")
                
                # Extract percentiles
                percentile_overall = firm.get("percentile_overall")
                percentile_model = firm.get("percentile_model")
                percentile_jurisdiction = firm.get("percentile_jurisdiction")
                
                # Extract pillar scores
                pillar_scores = firm.get("pillar_scores", {})
                
                # Extract metrics
                metrics = {
                    "na_rate": firm.get("na_rate"),
                    "jurisdiction_tier": firm.get("jurisdiction_tier"),
                    "model_type": firm.get("model_type"),
                    "payout_frequency": firm.get("payout_frequency"),
                }
                
                # Status and verdicts
                status = firm.get("status", "candidate")
                oversight_gate_verdict = firm.get("oversight_gate_verdict")
                audit_verdict = firm.get("audit_verdict")
                
                # Insert or update
                inserted = self._insert_snapshot_record(
                    firm_id=firm_id,
                    firm_name=firm_name,
                    score=float(score),
                    score_normalized=float(score_normalized),
                    integrity_score=firm.get("integrity_score"),
                    confidence=confidence,
                    percentile_overall=percentile_overall,
                    percentile_model=percentile_model,
                    percentile_jurisdiction=percentile_jurisdiction,
                    pillar_scores=pillar_scores,
                    metrics=metrics,
                    status=status,
                    oversight_gate_verdict=oversight_gate_verdict,
                    audit_verdict=audit_verdict,
                    snapshot_id=snapshot_id,
                    snapshot_hash=snapshot_hash,
                )
                
                if inserted:
                    count += 1
                    
            except Exception as e:
                print(f"Error capturing snapshot for {firm.get('firm_name', 'unknown')}: {e}")
                continue
        
        print(f"[SnapshotHistoryAgent] Captured {count} firm snapshots from {snapshot_id}")
        return count

    def _insert_snapshot_record(
        self,
        firm_id: str,
        firm_name: str,
        score: float,
        score_normalized: float,
        integrity_score: Optional[float],
        confidence: str,
        percentile_overall: Optional[float],
        percentile_model: Optional[float],
        percentile_jurisdiction: Optional[float],
        pillar_scores: Dict[str, float],
        metrics: Dict[str, Any],
        status: str,
        oversight_gate_verdict: Optional[str],
        audit_verdict: Optional[str],
        snapshot_id: str,
        snapshot_hash: str,
    ) -> bool:
        """Insert or update snapshot record"""
        try:
            # Check if already exists
            existing = fetchone(
                """
                SELECT id FROM firm_snapshots 
                WHERE firm_id = %s AND snapshot_id = %s
                """,
                (firm_id, snapshot_id),
            )
            
            if existing:
                # Update existing record
                execute(
                    """
                    UPDATE firm_snapshots 
                    SET 
                        score = %s,
                        score_normalized = %s,
                        integrity_score = %s,
                        confidence = %s,
                        percentile_overall = %s,
                        percentile_model = %s,
                        percentile_jurisdiction = %s,
                        pillar_scores = %s,
                        metrics = %s,
                        status = %s,
                        oversight_gate_verdict = %s,
                        audit_verdict = %s,
                        updated_at = NOW()
                    WHERE firm_id = %s AND snapshot_id = %s
                    """,
                    (
                        score,
                        score_normalized,
                        integrity_score,
                        confidence,
                        percentile_overall,
                        percentile_model,
                        percentile_jurisdiction,
                        json.dumps(pillar_scores or {}),
                        json.dumps(metrics or {}),
                        status,
                        oversight_gate_verdict,
                        audit_verdict,
                        firm_id,
                        snapshot_id,
                    ),
                )
                return False  # Already existed
            else:
                # Insert new record
                execute(
                    """
                    INSERT INTO firm_snapshots (
                        firm_id, firm_name, score, score_normalized, integrity_score,
                        confidence, percentile_overall, percentile_model, percentile_jurisdiction,
                        pillar_scores, metrics, status, oversight_gate_verdict, audit_verdict,
                        snapshot_id, snapshot_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        firm_id,
                        firm_name,
                        score,
                        score_normalized,
                        integrity_score,
                        confidence,
                        percentile_overall,
                        percentile_model,
                        percentile_jurisdiction,
                        json.dumps(pillar_scores or {}),
                        json.dumps(metrics or {}),
                        status,
                        oversight_gate_verdict,
                        audit_verdict,
                        snapshot_id,
                        snapshot_hash,
                    ),
                )
                return True
                
        except Exception as e:
            print(f"Error inserting snapshot record: {e}")
            return False

    def get_history(
        self, 
        firm_id: str, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve historical snapshots for a firm
        
        Args:
            firm_id: Firm identifier
            limit: Max records to return
            
        Returns:
            List of snapshot records sorted by date descending
        """
        records = fetchall(
            """
            SELECT 
                id,
                firm_id,
                firm_name,
                score,
                score_normalized,
                integrity_score,
                confidence,
                percentile_overall,
                percentile_model,
                percentile_jurisdiction,
                pillar_scores,
                metrics,
                status,
                oversight_gate_verdict,
                audit_verdict,
                snapshot_id,
                captured_at,
                created_at
            FROM firm_snapshots
            WHERE firm_id = %s
            ORDER BY captured_at DESC
            LIMIT %s
            """,
            (firm_id, limit),
        )
        
        return [
            {
                "date": record[16].isoformat() if record[16] else None,
                "score": float(record[3]) if record[3] else None,
                "confidence": record[7],
                "status": record[12],
                "percentile_overall": record[9],
                "pillar_scores": json.loads(record[10]) if record[10] else {},
                "snapshot_id": record[15],
            }
            for record in records
        ]

    def get_trajectory(self, firm_id: str, days: int = 90) -> List[Dict[str, Any]]:
        """
        Get score trajectory for analysis
        
        Args:
            firm_id: Firm identifier
            days: How many days back to look
            
        Returns:
            Simplified trajectory data for charting
        """
        records = fetchall(
            """
            SELECT 
                DATE(captured_at) as date,
                AVG(score) as avg_score,
                MIN(score) as min_score,
                MAX(score) as max_score,
                COUNT(*) as snapshot_count
            FROM firm_snapshots
            WHERE firm_id = %s
              AND captured_at >= NOW() - INTERVAL '%s days'
            GROUP BY DATE(captured_at)
            ORDER BY date ASC
            """,
            (firm_id, days),
        )
        
        return [
            {
                "date": record[0].isoformat(),
                "score": float(record[1]) if record[1] else None,
                "min_score": float(record[2]) if record[2] else None,
                "max_score": float(record[3]) if record[3] else None,
                "count": record[4],
            }
            for record in records
        ]


# Singleton instance
_agent_instance: Optional[SnapshotHistoryAgent] = None


def get_snapshot_history_agent() -> SnapshotHistoryAgent:
    """Get or create snapshot history agent instance"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = SnapshotHistoryAgent()
    return _agent_instance
