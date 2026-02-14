"""
Validation Test 1: Coverage & Data Sufficiency
Created: 2026-02-01
Phase: 1 (Validation Framework)

Purpose:
- Ensure adequate data coverage across all firms in the universe
- Verify no firm has excessive NA (Not Available) rate
- Track Agent C (oversight gate) pass rates
- Monitor data completeness by jurisdiction

Success Criteria (v1.1):
- Data coverage > 85%
- Average NA rate < 25%
- Agent C pass rate > 75%

IOSCO Alignment: Article 13 (Methodology Transparency)
"""

from typing import Dict, List, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class CoverageTest:
    """Test 1: Coverage & Data Sufficiency validation"""
    
    def __init__(self, snapshot_data: Dict[str, Any]):
        """
        Initialize coverage test with snapshot data
        
        Args:
            snapshot_data: Complete snapshot with records and metadata
        """
        self.snapshot = snapshot_data
        self.records = snapshot_data.get("records", [])
        self.metadata = snapshot_data.get("metadata", {})
        self.results = {}
    
    def run(self) -> Dict[str, Any]:
        """
        Execute all coverage tests
        
        Returns:
            Dictionary with test results and pass/fail status
        """
        logger.info("Running Coverage & Data Sufficiency test...")
        
        self.results = {
            "test_name": "coverage_data_sufficiency",
            "timestamp": datetime.utcnow().isoformat(),
            "snapshot_id": self.metadata.get("version", "unknown"),
            "total_firms": len(self.records),
            "passed": False,
            "metrics": {},
            "alerts": [],
            "details": {}
        }
        
        # Test 1.1: Overall coverage
        self._test_overall_coverage()
        
        # Test 1.2: NA rate analysis
        self._test_na_rates()
        
        # Test 1.3: Agent C pass rate
        self._test_agent_c_pass_rate()
        
        # Test 1.4: Coverage by jurisdiction
        self._test_jurisdiction_coverage()
        
        # Test 1.5: Critical fields completeness
        self._test_critical_fields()
        
        # Determine overall pass/fail
        self._determine_pass_fail()
        
        logger.info(f"Coverage test complete: {'PASS' if self.results['passed'] else 'FAIL'}")
        return self.results
    
    def _test_overall_coverage(self):
        """Test overall data coverage percentage"""
        total_firms = len(self.records)
        
        # Calculate average NA rate
        na_rates = [r.get("na_rate", 0) for r in self.records]
        avg_na_rate = sum(na_rates) / total_firms if total_firms > 0 else 100
        
        # Coverage = (100 - avg_na_rate)
        coverage_percent = 100 - avg_na_rate
        
        self.results["metrics"]["coverage_percent"] = round(coverage_percent, 2)
        self.results["metrics"]["avg_na_rate"] = round(avg_na_rate, 2)
        
        if coverage_percent < 85:
            self.results["alerts"].append(
                f"Low coverage: {coverage_percent:.1f}% (target: >85%)"
            )
        
        logger.info(f"Coverage: {coverage_percent:.1f}%, Avg NA rate: {avg_na_rate:.1f}%")
    
    def _test_na_rates(self):
        """Test individual firm NA rates"""
        na_rates = [r.get("na_rate", 0) for r in self.records]
        
        # Find firms with high NA rates
        high_na_firms = [
            {"firm_id": r["firm_id"], "na_rate": r.get("na_rate", 0)}
            for r in self.records
            if r.get("na_rate", 0) > 40
        ]
        
        self.results["details"]["high_na_firms_count"] = len(high_na_firms)
        self.results["details"]["high_na_firms"] = high_na_firms[:10]  # Top 10
        
        # Distribution
        na_distribution = {
            "0-10%": len([r for r in na_rates if r <= 10]),
            "11-25%": len([r for r in na_rates if 10 < r <= 25]),
            "26-40%": len([r for r in na_rates if 25 < r <= 40]),
            ">40%": len([r for r in na_rates if r > 40])
        }
        
        self.results["details"]["na_distribution"] = na_distribution
        
        if len(high_na_firms) > len(self.records) * 0.1:
            self.results["alerts"].append(
                f"{len(high_na_firms)} firms have NA rate >40% (>{len(self.records) * 0.1:.0f} threshold)"
            )
    
    def _test_agent_c_pass_rate(self):
        """Test Agent C (oversight gate) pass rate"""
        total_firms = len(self.records)
        
        # Agent C passes if NA rate <= 75% (i.e., coverage >= 25%)
        passed_firms = [r for r in self.records if r.get("na_rate", 100) <= 75]
        pass_rate = (len(passed_firms) / total_firms * 100) if total_firms > 0 else 0
        
        self.results["metrics"]["agent_c_pass_rate"] = round(pass_rate, 2)
        self.results["details"]["agent_c_passed_firms"] = len(passed_firms)
        self.results["details"]["agent_c_failed_firms"] = total_firms - len(passed_firms)
        
        if pass_rate < 75:
            self.results["alerts"].append(
                f"Low Agent C pass rate: {pass_rate:.1f}% (target: >75%)"
            )
        
        logger.info(f"Agent C pass rate: {pass_rate:.1f}%")
    
    def _test_jurisdiction_coverage(self):
        """Test coverage breakdown by jurisdiction tier"""
        jurisdiction_stats = {}
        
        for record in self.records:
            jur = record.get("jurisdiction_tier", "UNKNOWN")
            if jur not in jurisdiction_stats:
                jurisdiction_stats[jur] = {
                    "count": 0,
                    "total_na_rate": 0,
                    "firms": []
                }
            
            jurisdiction_stats[jur]["count"] += 1
            jurisdiction_stats[jur]["total_na_rate"] += record.get("na_rate", 0)
            jurisdiction_stats[jur]["firms"].append(record["firm_id"])
        
        # Calculate averages
        for jur, stats in jurisdiction_stats.items():
            stats["avg_na_rate"] = round(
                stats["total_na_rate"] / stats["count"], 2
            ) if stats["count"] > 0 else 0
            stats["coverage_percent"] = round(100 - stats["avg_na_rate"], 2)
            # Don't store full firm list in results
            del stats["firms"]
            del stats["total_na_rate"]
        
        self.results["details"]["by_jurisdiction"] = jurisdiction_stats
        
        # Check for jurisdictions with poor coverage
        poor_coverage_jur = [
            jur for jur, stats in jurisdiction_stats.items()
            if stats["coverage_percent"] < 70
        ]
        
        if poor_coverage_jur:
            self.results["alerts"].append(
                f"Poor coverage in jurisdictions: {', '.join(poor_coverage_jur)}"
            )
    
    def _test_critical_fields(self):
        """Test completeness of critical fields (score, jurisdiction, confidence)"""
        critical_fields = ["score_0_100", "jurisdiction_tier", "confidence"]
        
        field_completeness = {}
        for field in critical_fields:
            complete_count = len([
                r for r in self.records
                if r.get(field) is not None and r.get(field) != ""
            ])
            completeness = (complete_count / len(self.records) * 100) if self.records else 0
            field_completeness[field] = round(completeness, 2)
        
        self.results["details"]["critical_fields_completeness"] = field_completeness
        
        # Alert if any critical field <95% complete
        incomplete_fields = [
            field for field, percent in field_completeness.items()
            if percent < 95
        ]
        
        if incomplete_fields:
            self.results["alerts"].append(
                f"Critical fields incomplete: {', '.join(incomplete_fields)}"
            )
    
    def _determine_pass_fail(self):
        """Determine overall test pass/fail based on success criteria"""
        coverage = self.results["metrics"].get("coverage_percent", 0)
        avg_na = self.results["metrics"].get("avg_na_rate", 100)
        agent_c = self.results["metrics"].get("agent_c_pass_rate", 0)
        
        # All criteria must pass
        criteria_met = (
            coverage > 85 and
            avg_na < 25 and
            agent_c > 75
        )
        
        self.results["passed"] = criteria_met
        self.results["success_criteria"] = {
            "coverage_gt_85": coverage > 85,
            "na_rate_lt_25": avg_na < 25,
            "agent_c_gt_75": agent_c > 75
        }


def run_coverage_test(snapshot_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to run coverage test
    
    Args:
        snapshot_data: Complete snapshot dictionary
        
    Returns:
        Test results dictionary
    """
    test = CoverageTest(snapshot_data)
    return test.run()


# Example usage
if __name__ == "__main__":
    import json
    from pathlib import Path
    
    # Load test snapshot
    snapshot_path = Path(__file__).parent.parent.parent.parent / "gpti-site" / "data" / "test-snapshot.json"
    
    if snapshot_path.exists():
        with open(snapshot_path) as f:
            snapshot = json.load(f)
        
        results = run_coverage_test(snapshot)
        
        print("\n=== Coverage Test Results ===")
        print(f"Status: {'✅ PASS' if results['passed'] else '❌ FAIL'}")
        print(f"Total firms: {results['total_firms']}")
        print(f"Coverage: {results['metrics']['coverage_percent']}%")
        print(f"Avg NA rate: {results['metrics']['avg_na_rate']}%")
        print(f"Agent C pass rate: {results['metrics']['agent_c_pass_rate']}%")
        
        if results['alerts']:
            print("\nAlerts:")
            for alert in results['alerts']:
                print(f"  ⚠️  {alert}")
        
        print(f"\nSuccess criteria:")
        for criterion, met in results['success_criteria'].items():
            status = "✅" if met else "❌"
            print(f"  {status} {criterion}")
    else:
        print(f"Test snapshot not found: {snapshot_path}")
