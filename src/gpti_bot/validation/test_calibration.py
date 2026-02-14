"""
Validation Test 5: Calibration & Bias Detection
Created: 2026-02-01
Phase: 1 (Validation Framework) - Week 3

Purpose:
- Verify confidence levels are accurate
- Detect bias across jurisdictions
- Ensure fair treatment regardless of firm size/location
- Validate model calibration

Success Criteria (v1.1):
- Confidence accuracy > 80%
- No systematic bias by jurisdiction
- Score distribution roughly normal
- High-confidence predictions more accurate

IOSCO Alignment: Article 13 (Methodology Transparency)
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class CalibrationTest:
    """Test 5: Calibration & Bias Detection validation"""
    
    def __init__(self, snapshot_data: Dict[str, Any]):
        """
        Initialize calibration test with snapshot data
        
        Args:
            snapshot_data: Complete snapshot with records and metadata
        """
        self.snapshot = snapshot_data
        self.records = snapshot_data.get("records", [])
        self.metadata = snapshot_data.get("metadata", {})
        self.results = {}
    
    def run(self) -> Dict[str, Any]:
        """
        Execute all calibration tests
        
        Returns:
            Dictionary with test results and pass/fail status
        """
        logger.info("Running Calibration & Bias Detection test...")
        
        self.results = {
            "test_name": "calibration_bias",
            "timestamp": datetime.utcnow().isoformat(),
            "snapshot_id": self.metadata.get("version", "unknown"),
            "total_firms": len(self.records),
            "passed": False,
            "metrics": {},
            "alerts": [],
            "details": {}
        }
        
        # Test 5.1: Confidence calibration
        self._test_confidence_calibration()
        
        # Test 5.2: Jurisdiction bias detection
        self._test_jurisdiction_bias()
        
        # Test 5.3: Score distribution analysis
        self._test_score_distribution()
        
        # Test 5.4: Confidence-accuracy correlation
        self._test_confidence_accuracy()
        
        # Test 5.5: Firm size bias (if data available)
        self._test_size_bias()
        
        # Determine overall pass/fail
        self._determine_pass_fail()
        
        logger.info(f"Calibration test complete: {'PASS' if self.results['passed'] else 'FAIL'}")
        return self.results
    
    def _test_confidence_calibration(self):
        """Test if confidence levels match actual data quality"""
        confidence_stats = {
            'high': {'count': 0, 'avg_na_rate': 0, 'avg_score': 0},
            'medium': {'count': 0, 'avg_na_rate': 0, 'avg_score': 0},
            'low': {'count': 0, 'avg_na_rate': 0, 'avg_score': 0}
        }
        
        for record in self.records:
            conf = record.get('confidence', 'medium')
            if conf not in confidence_stats:
                conf = 'medium'
            
            confidence_stats[conf]['count'] += 1
            confidence_stats[conf]['avg_na_rate'] += record.get('na_rate', 0)
            confidence_stats[conf]['avg_score'] += record.get('score_0_100', 0)
        
        # Calculate averages
        for conf, stats in confidence_stats.items():
            if stats['count'] > 0:
                stats['avg_na_rate'] = round(stats['avg_na_rate'] / stats['count'], 2)
                stats['avg_score'] = round(stats['avg_score'] / stats['count'], 2)
        
        self.results['details']['confidence_calibration'] = confidence_stats
        
        # Verify: high confidence should have lower NA rate
        if confidence_stats['high']['count'] > 0 and confidence_stats['low']['count'] > 0:
            if confidence_stats['high']['avg_na_rate'] >= confidence_stats['low']['avg_na_rate']:
                self.results['alerts'].append(
                    "Confidence calibration issue: High confidence has higher NA rate than low"
                )
        
        # Calculate overall confidence accuracy (simplified metric)
        total_firms = len(self.records)
        expected_high = confidence_stats['high']['count'] / total_firms if total_firms > 0 else 0
        
        # We expect high confidence firms to have <15% NA rate
        high_conf_accurate = sum(
            1 for r in self.records 
            if r.get('confidence') == 'high' and r.get('na_rate', 100) < 15
        )
        
        if confidence_stats['high']['count'] > 0:
            accuracy = (high_conf_accurate / confidence_stats['high']['count']) * 100
            self.results['metrics']['confidence_accuracy'] = round(accuracy, 2)
        else:
            self.results['metrics']['confidence_accuracy'] = 0
        
        logger.info(f"Confidence calibration: {confidence_stats}")
    
    def _test_jurisdiction_bias(self):
        """Test for systematic bias across jurisdictions"""
        jurisdiction_stats = {}
        
        for record in self.records:
            jur = record.get('jurisdiction_tier', 'UNKNOWN')
            if jur not in jurisdiction_stats:
                jurisdiction_stats[jur] = {
                    'count': 0,
                    'total_score': 0,
                    'scores': []
                }
            
            jurisdiction_stats[jur]['count'] += 1
            jurisdiction_stats[jur]['total_score'] += record.get('score_0_100', 0)
            jurisdiction_stats[jur]['scores'].append(record.get('score_0_100', 0))
        
        # Calculate average scores and variance
        for jur, stats in jurisdiction_stats.items():
            if stats['count'] > 0:
                avg_score = stats['total_score'] / stats['count']
                stats['avg_score'] = round(avg_score, 2)
                
                # Calculate variance
                variance = sum((s - avg_score) ** 2 for s in stats['scores']) / stats['count']
                stats['std_dev'] = round(variance ** 0.5, 2)
                
                # Remove raw scores list from output
                del stats['scores']
        
        self.results['details']['jurisdiction_stats'] = jurisdiction_stats
        
        # Check for outliers (jurisdiction with significantly different avg score)
        if jurisdiction_stats:
            all_avg_scores = [s['avg_score'] for s in jurisdiction_stats.values()]
            global_avg = sum(all_avg_scores) / len(all_avg_scores)
            global_std = (sum((s - global_avg) ** 2 for s in all_avg_scores) / len(all_avg_scores)) ** 0.5
            
            # Flag jurisdictions more than 1.5 std devs from mean
            for jur, stats in jurisdiction_stats.items():
                if abs(stats['avg_score'] - global_avg) > 1.5 * global_std:
                    self.results['alerts'].append(
                        f"Potential bias: Jurisdiction {jur} avg score {stats['avg_score']} "
                        f"deviates from global avg {global_avg:.2f}"
                    )
        
        self.results['metrics']['jurisdiction_score_variance'] = round(
            max([s.get('std_dev', 0) for s in jurisdiction_stats.values()]) if jurisdiction_stats else 0,
            2
        )
        
        logger.info(f"Jurisdiction bias analysis complete: {len(jurisdiction_stats)} tiers")
    
    def _test_score_distribution(self):
        """Test if score distribution is reasonable (roughly normal)"""
        scores = [r.get('score_0_100', 0) for r in self.records]
        
        if not scores:
            return
        
        # Calculate distribution metrics
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5
        
        # Calculate skewness (simplified)
        skewness = sum((s - mean) ** 3 for s in scores) / (len(scores) * std_dev ** 3) if std_dev > 0 else 0
        
        # Score ranges
        score_ranges = {
            '0-20': len([s for s in scores if s <= 20]),
            '21-40': len([s for s in scores if 20 < s <= 40]),
            '41-60': len([s for s in scores if 40 < s <= 60]),
            '61-80': len([s for s in scores if 60 < s <= 80]),
            '81-100': len([s for s in scores if s > 80])
        }
        
        self.results['metrics']['score_mean'] = round(mean, 2)
        self.results['metrics']['score_std_dev'] = round(std_dev, 2)
        self.results['metrics']['score_skewness'] = round(skewness, 4)
        self.results['details']['score_distribution'] = score_ranges
        
        # Check for extreme skewness
        if abs(skewness) > 2:
            self.results['alerts'].append(
                f"High score skewness: {skewness:.2f} (indicates potential bias)"
            )
        
        # Check for missing ranges (potential clustering)
        empty_ranges = [r for r, count in score_ranges.items() if count == 0]
        if len(empty_ranges) > 2:
            self.results['alerts'].append(
                f"Score clustering detected: {len(empty_ranges)} empty ranges"
            )
        
        logger.info(f"Score distribution: mean={mean:.2f}, std={std_dev:.2f}, skew={skewness:.4f}")
    
    def _test_confidence_accuracy(self):
        """Test if higher confidence correlates with better data quality"""
        # Group by confidence level
        by_confidence = {
            'high': [],
            'medium': [],
            'low': []
        }
        
        for record in self.records:
            conf = record.get('confidence', 'medium')
            na_rate = record.get('na_rate', 100)
            by_confidence[conf].append(na_rate)
        
        # Calculate average NA rates
        avg_na_by_conf = {}
        for conf, na_rates in by_confidence.items():
            if na_rates:
                avg_na_by_conf[conf] = round(sum(na_rates) / len(na_rates), 2)
            else:
                avg_na_by_conf[conf] = None
        
        self.results['details']['confidence_accuracy_correlation'] = avg_na_by_conf
        
        # Verify ordering: high < medium < low NA rate
        if (avg_na_by_conf.get('high') is not None and 
            avg_na_by_conf.get('medium') is not None and
            avg_na_by_conf.get('low') is not None):
            
            correct_ordering = (
                avg_na_by_conf['high'] < avg_na_by_conf['medium'] < avg_na_by_conf['low']
            )
            
            if not correct_ordering:
                self.results['alerts'].append(
                    "Confidence-accuracy mismatch: NA rates don't decrease with higher confidence"
                )
        
        logger.info(f"Confidence-accuracy correlation: {avg_na_by_conf}")
    
    def _test_size_bias(self):
        """Test for bias based on firm size (if data available)"""
        # Check if we have size indicators in detailed_metrics
        has_size_data = any(
            'size' in str(r.get('detailed_metrics', {})).lower()
            for r in self.records[:5]  # Sample first 5
        )
        
        if not has_size_data:
            self.results['details']['size_bias'] = "No size data available"
            logger.info("Size bias test skipped: no size data")
            return
        
        # If size data exists, analyze
        # This is a placeholder for when real size data is available
        self.results['details']['size_bias'] = "Data available but not yet analyzed"
    
    def _determine_pass_fail(self):
        """Determine overall test pass/fail based on success criteria"""
        confidence_accuracy = self.results['metrics'].get('confidence_accuracy', 0)
        score_skewness = abs(self.results['metrics'].get('score_skewness', 0))
        
        # Success criteria:
        # 1. Confidence accuracy > 80%
        # 2. Score skewness < 2 (not too biased)
        # 3. No critical bias alerts
        
        critical_alerts = len([
            a for a in self.results['alerts']
            if 'bias' in a.lower() or 'calibration issue' in a.lower()
        ])
        
        criteria_met = (
            confidence_accuracy > 80 and
            score_skewness < 2 and
            critical_alerts == 0
        )
        
        self.results['passed'] = criteria_met
        self.results['success_criteria'] = {
            'confidence_accuracy_gt_80': confidence_accuracy > 80,
            'score_skewness_lt_2': score_skewness < 2,
            'no_critical_bias': critical_alerts == 0
        }


def run_calibration_test(snapshot_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to run calibration test
    
    Args:
        snapshot_data: Complete snapshot dictionary
        
    Returns:
        Test results dictionary
    """
    test = CalibrationTest(snapshot_data)
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
        
        results = run_calibration_test(snapshot)
        
        print("\n=== Calibration Test Results ===")
        print(f"Status: {'✅ PASS' if results['passed'] else '❌ FAIL'}")
        print(f"Total firms: {results['total_firms']}")
        print(f"Confidence accuracy: {results['metrics'].get('confidence_accuracy', 'N/A')}%")
        print(f"Score mean: {results['metrics'].get('score_mean', 'N/A')}")
        print(f"Score std dev: {results['metrics'].get('score_std_dev', 'N/A')}")
        print(f"Score skewness: {results['metrics'].get('score_skewness', 'N/A')}")
        
        if results['alerts']:
            print("\nAlerts:")
            for alert in results['alerts']:
                print(f"  ⚠️  {alert}")
        
        print("\nSuccess criteria:")
        for criterion, met in results['success_criteria'].items():
            status = "✅" if met else "❌"
            print(f"  {status} {criterion}")
    else:
        print(f"Test snapshot not found: {snapshot_path}")
