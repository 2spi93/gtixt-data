"""
Validation Test 2: Stability & Turnover
Created: 2026-02-01
Phase: 1 (Validation Framework)

Purpose:
- Verify scores are stable between snapshots (no erratic changes)
- Track turnover in top 10/20 rankings
- Detect firms with major score changes
- Ensure deterministic scoring

Success Criteria (v1.1):
- Avg score change < 0.05
- Top 10 turnover ≤ 2 firms
- Top 20 turnover ≤ 4 firms
- <5% of firms have major changes (>10 points)

IOSCO Alignment: Article 14 (Quality of Benchmark)
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class StabilityTest:
    """Test 2: Stability & Turnover validation"""
    
    def __init__(
        self, 
        current_snapshot: Dict[str, Any],
        previous_snapshot: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize stability test with current and previous snapshots
        
        Args:
            current_snapshot: Latest snapshot data
            previous_snapshot: Previous snapshot for comparison (optional)
        """
        self.current = current_snapshot
        self.previous = previous_snapshot
        self.current_records = current_snapshot.get("records", [])
        self.previous_records = previous_snapshot.get("records", []) if previous_snapshot else []
        self.results = {}
    
    def run(self) -> Dict[str, Any]:
        """
        Execute all stability tests
        
        Returns:
            Dictionary with test results and pass/fail status
        """
        logger.info("Running Stability & Turnover test...")
        
        self.results = {
            "test_name": "stability_turnover",
            "timestamp": datetime.utcnow().isoformat(),
            "current_snapshot_id": self.current.get("metadata", {}).get("version", "unknown"),
            "previous_snapshot_id": self.previous.get("metadata", {}).get("version", "N/A") if self.previous else "N/A",
            "has_historical_data": bool(self.previous),
            "passed": False,
            "metrics": {},
            "alerts": [],
            "details": {}
        }
        
        if not self.previous:
            logger.warning("No previous snapshot for comparison - stability test limited")
            self.results["alerts"].append(
                "No historical data available - cannot perform full stability analysis"
            )
            # Perform single-snapshot analysis only
            self._analyze_current_snapshot_only()
            self.results["passed"] = True  # Pass by default without historical data
        else:
            # Test 2.1: Score change analysis
            self._test_score_changes()
            
            # Test 2.2: Top 10 turnover
            self._test_top_10_turnover()
            
            # Test 2.3: Top 20 turnover
            self._test_top_20_turnover()
            
            # Test 2.4: Major score changes
            self._test_major_changes()
            
            # Test 2.5: Score volatility by jurisdiction
            self._test_jurisdiction_volatility()
            
            # Determine overall pass/fail
            self._determine_pass_fail()
        
        logger.info(f"Stability test complete: {'PASS' if self.results['passed'] else 'FAIL'}")
        return self.results
    
    def _analyze_current_snapshot_only(self):
        """Analyze current snapshot when no historical data available"""
        scores = [r.get("score_0_100", 0) for r in self.current_records]
        
        if scores:
            self.results["metrics"]["avg_score"] = round(sum(scores) / len(scores), 2)
            self.results["metrics"]["min_score"] = min(scores)
            self.results["metrics"]["max_score"] = max(scores)
            self.results["metrics"]["score_range"] = max(scores) - min(scores)
        
        # Get top 10 for reference
        top_10 = sorted(
            self.current_records,
            key=lambda x: x.get("score_0_100", 0),
            reverse=True
        )[:10]
        
        self.results["details"]["current_top_10"] = [
            {"firm_id": r["firm_id"], "score": r.get("score_0_100")}
            for r in top_10
        ]
        
        logger.info("Single snapshot analysis complete (no historical comparison)")
    
    def _test_score_changes(self):
        """Test average score change between snapshots"""
        # Build lookup dict for previous scores
        prev_scores = {
            r["firm_id"]: r.get("score_0_100", 0)
            for r in self.previous_records
        }
        
        score_changes = []
        for record in self.current_records:
            firm_id = record["firm_id"]
            current_score = record.get("score_0_100", 0)
            
            if firm_id in prev_scores:
                prev_score = prev_scores[firm_id]
                change = abs(current_score - prev_score)
                score_changes.append({
                    "firm_id": firm_id,
                    "previous": prev_score,
                    "current": current_score,
                    "change": change
                })
        
        if score_changes:
            avg_change = sum(c["change"] for c in score_changes) / len(score_changes)
            median_change = sorted([c["change"] for c in score_changes])[len(score_changes) // 2]
            max_change = max(c["change"] for c in score_changes)
            
            self.results["metrics"]["avg_score_change"] = round(avg_change, 4)
            self.results["metrics"]["median_score_change"] = round(median_change, 4)
            self.results["metrics"]["max_score_change"] = round(max_change, 4)
            self.results["details"]["firms_compared"] = len(score_changes)
            
            # Get top 5 largest changes
            largest_changes = sorted(score_changes, key=lambda x: x["change"], reverse=True)[:5]
            self.results["details"]["largest_changes"] = largest_changes
            
            if avg_change >= 0.05:
                self.results["alerts"].append(
                    f"High average score change: {avg_change:.4f} (threshold: <0.05)"
                )
            
            logger.info(f"Avg score change: {avg_change:.4f}, Max: {max_change:.2f}")
        else:
            logger.warning("No firms found in both snapshots for comparison")
            self.results["alerts"].append("No common firms between snapshots")
    
    def _test_top_10_turnover(self):
        """Test turnover in top 10 rankings"""
        # Get top 10 from both snapshots
        current_top_10 = set([
            r["firm_id"] for r in sorted(
                self.current_records,
                key=lambda x: x.get("score_0_100", 0),
                reverse=True
            )[:10]
        ])
        
        previous_top_10 = set([
            r["firm_id"] for r in sorted(
                self.previous_records,
                key=lambda x: x.get("score_0_100", 0),
                reverse=True
            )[:10]
        ])
        
        # Calculate turnover (firms that left top 10)
        left_top_10 = previous_top_10 - current_top_10
        entered_top_10 = current_top_10 - previous_top_10
        turnover = len(left_top_10)
        
        self.results["metrics"]["top_10_turnover"] = turnover
        self.results["details"]["left_top_10"] = list(left_top_10)
        self.results["details"]["entered_top_10"] = list(entered_top_10)
        self.results["details"]["current_top_10_ids"] = list(current_top_10)
        
        if turnover > 2:
            self.results["alerts"].append(
                f"High top 10 turnover: {turnover} firms (threshold: ≤2)"
            )
        
        logger.info(f"Top 10 turnover: {turnover} firms")
    
    def _test_top_20_turnover(self):
        """Test turnover in top 20 rankings"""
        current_top_20 = set([
            r["firm_id"] for r in sorted(
                self.current_records,
                key=lambda x: x.get("score_0_100", 0),
                reverse=True
            )[:20]
        ])
        
        previous_top_20 = set([
            r["firm_id"] for r in sorted(
                self.previous_records,
                key=lambda x: x.get("score_0_100", 0),
                reverse=True
            )[:20]
        ])
        
        turnover = len(previous_top_20 - current_top_20)
        
        self.results["metrics"]["top_20_turnover"] = turnover
        
        if turnover > 4:
            self.results["alerts"].append(
                f"High top 20 turnover: {turnover} firms (threshold: ≤4)"
            )
        
        logger.info(f"Top 20 turnover: {turnover} firms")
    
    def _test_major_changes(self):
        """Test for firms with major score changes (>10 points)"""
        prev_scores = {
            r["firm_id"]: r.get("score_0_100", 0)
            for r in self.previous_records
        }
        
        major_changes = []
        for record in self.current_records:
            firm_id = record["firm_id"]
            current_score = record.get("score_0_100", 0)
            
            if firm_id in prev_scores:
                prev_score = prev_scores[firm_id]
                change = current_score - prev_score
                
                if abs(change) > 10:
                    major_changes.append({
                        "firm_id": firm_id,
                        "previous": prev_score,
                        "current": current_score,
                        "change": round(change, 2),
                        "direction": "increase" if change > 0 else "decrease"
                    })
        
        self.results["metrics"]["firms_with_major_changes"] = len(major_changes)
        self.results["details"]["major_changes"] = major_changes
        
        # Threshold: <5% of firms should have major changes
        threshold_count = len(self.current_records) * 0.05
        
        if len(major_changes) > threshold_count:
            self.results["alerts"].append(
                f"{len(major_changes)} firms with major changes (threshold: <{threshold_count:.0f})"
            )
        
        logger.info(f"Firms with major changes (>10 pts): {len(major_changes)}")
    
    def _test_jurisdiction_volatility(self):
        """Test score volatility by jurisdiction tier"""
        prev_scores_by_jur = {}
        for r in self.previous_records:
            jur = r.get("jurisdiction_tier", "UNKNOWN")
            if jur not in prev_scores_by_jur:
                prev_scores_by_jur[jur] = {}
            prev_scores_by_jur[jur][r["firm_id"]] = r.get("score_0_100", 0)
        
        jur_volatility = {}
        for r in self.current_records:
            jur = r.get("jurisdiction_tier", "UNKNOWN")
            firm_id = r["firm_id"]
            current_score = r.get("score_0_100", 0)
            
            if jur in prev_scores_by_jur and firm_id in prev_scores_by_jur[jur]:
                prev_score = prev_scores_by_jur[jur][firm_id]
                change = abs(current_score - prev_score)
                
                if jur not in jur_volatility:
                    jur_volatility[jur] = []
                jur_volatility[jur].append(change)
        
        # Calculate average volatility per jurisdiction
        jur_stats = {}
        for jur, changes in jur_volatility.items():
            if changes:
                jur_stats[jur] = {
                    "avg_change": round(sum(changes) / len(changes), 4),
                    "max_change": round(max(changes), 2),
                    "firms_compared": len(changes)
                }
        
        self.results["details"]["jurisdiction_volatility"] = jur_stats
        
        logger.info(f"Jurisdiction volatility calculated for {len(jur_stats)} tiers")
    
    def _determine_pass_fail(self):
        """Determine overall test pass/fail based on success criteria"""
        avg_change = self.results["metrics"].get("avg_score_change", 0)
        top_10 = self.results["metrics"].get("top_10_turnover", 0)
        top_20 = self.results["metrics"].get("top_20_turnover", 0)
        major_changes = self.results["metrics"].get("firms_with_major_changes", 0)
        
        threshold_major = len(self.current_records) * 0.05
        
        criteria_met = (
            avg_change < 0.05 and
            top_10 <= 2 and
            top_20 <= 4 and
            major_changes < threshold_major
        )
        
        self.results["passed"] = criteria_met
        self.results["success_criteria"] = {
            "avg_change_lt_0_05": avg_change < 0.05,
            "top_10_turnover_lte_2": top_10 <= 2,
            "top_20_turnover_lte_4": top_20 <= 4,
            "major_changes_lt_5pct": major_changes < threshold_major
        }


def run_stability_test(
    current_snapshot: Dict[str, Any],
    previous_snapshot: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convenience function to run stability test
    
    Args:
        current_snapshot: Latest snapshot dictionary
        previous_snapshot: Previous snapshot for comparison (optional)
        
    Returns:
        Test results dictionary
    """
    test = StabilityTest(current_snapshot, previous_snapshot)
    return test.run()


# Example usage
if __name__ == "__main__":
    import json
    from pathlib import Path
    
    # Load test snapshot
    snapshot_path = Path("/opt/gpti/gpti-site/data/test-snapshot.json")
    
    if snapshot_path.exists():
        with open(snapshot_path) as f:
            snapshot = json.load(f)
        
        # For testing, use same snapshot as "previous" (zero changes expected)
        results = run_stability_test(snapshot, snapshot)
        
        print("\n=== Stability Test Results ===")
        print(f"Status: {'✅ PASS' if results['passed'] else '❌ FAIL'}")
        print(f"Has historical data: {results['has_historical_data']}")
        
        if results['has_historical_data']:
            print(f"Avg score change: {results['metrics'].get('avg_score_change', 'N/A')}")
            print(f"Top 10 turnover: {results['metrics'].get('top_10_turnover', 'N/A')}")
            print(f"Top 20 turnover: {results['metrics'].get('top_20_turnover', 'N/A')}")
            print(f"Major changes: {results['metrics'].get('firms_with_major_changes', 'N/A')}")
        
        if results['alerts']:
            print("\nAlerts:")
            for alert in results['alerts']:
                print(f"  ⚠️  {alert}")
    else:
        print(f"Test snapshot not found: {snapshot_path}")
