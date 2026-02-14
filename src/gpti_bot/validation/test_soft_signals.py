"""
Validation Test 4: Soft Signals Detection
Created: 2026-02-01
Phase: 1 (Validation Framework) - Week 4

Purpose:
- Track Reddit/TrustPilot sentiment changes
- Detect early warnings of unreported issues
- Monitor social media and review platforms
- Alert on sudden negative sentiment shifts

Success Criteria (v1.1):
- Detect sentiment changes within 48 hours
- 85%+ accuracy on sentiment classification
- <5% false positive rate
- Correlate soft signals with hard data

IOSCO Alignment: Article 13 (Methodology Transparency)
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class SoftSignalsTest:
    """Test 4: Soft Signals Detection validation"""
    
    def __init__(
        self,
        snapshot_data: Dict[str, Any],
        sentiment_data: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Initialize soft signals test with snapshot and sentiment data
        
        Args:
            snapshot_data: Complete snapshot with records and metadata
            sentiment_data: List of sentiment signals (Reddit, TrustPilot, etc.)
        """
        self.snapshot = snapshot_data
        self.records = snapshot_data.get("records", [])
        self.metadata = snapshot_data.get("metadata", {})
        self.signals = sentiment_data or []
        self.results = {}
        
        # Build firm lookup
        self.firms_by_id = {r['firm_id']: r for r in self.records}
    
    def run(self) -> Dict[str, Any]:
        """
        Execute all soft signals detection tests
        
        Returns:
            Dictionary with test results and pass/fail status
        """
        logger.info("Running Soft Signals Detection test...")
        
        self.results = {
            "test_name": "soft_signals",
            "timestamp": datetime.utcnow().isoformat(),
            "snapshot_id": self.metadata.get("version", "unknown"),
            "total_firms": len(self.records),
            "total_signals": len(self.signals),
            "passed": False,
            "metrics": {},
            "alerts": [],
            "details": {}
        }
        
        if not self.signals:
            logger.warning("No sentiment data provided - test limited")
            self.results['alerts'].append("No sentiment signals available for analysis")
            self.results['status'] = "LIMITED"
            return self.results
        
        # Test 4.1: Sentiment detection rate
        self._test_sentiment_detection()
        
        # Test 4.2: Signal-score correlation
        self._test_signal_correlation()
        
        # Test 4.3: Early warning detection
        self._test_early_warnings()
        
        # Test 4.4: False positive rate
        self._test_false_positives()
        
        # Test 4.5: Multi-source validation
        self._test_multi_source_validation()
        
        # Determine overall pass/fail
        self._determine_pass_fail()
        
        logger.info(f"Soft signals test complete: {'PASS' if self.results['passed'] else 'FAIL'}")
        return self.results
    
    def _test_sentiment_detection(self):
        """Test if sentiment signals are detected and categorized"""
        sentiment_by_type = defaultdict(int)
        sentiment_by_source = defaultdict(int)
        sentiment_by_firm = defaultdict(list)
        
        for signal in self.signals:
            signal_type = signal.get('sentiment', 'neutral')
            source = signal.get('source', 'unknown')
            firm_id = signal.get('firm_id')
            
            sentiment_by_type[signal_type] += 1
            sentiment_by_source[source] += 1
            
            if firm_id:
                sentiment_by_firm[firm_id].append(signal)
        
        # Calculate detection metrics
        total_signals = len(self.signals)
        negative_signals = sentiment_by_type.get('negative', 0)
        positive_signals = sentiment_by_type.get('positive', 0)
        neutral_signals = sentiment_by_type.get('neutral', 0)
        
        self.results['metrics']['total_signals_analyzed'] = total_signals
        self.results['metrics']['negative_signals'] = negative_signals
        self.results['metrics']['positive_signals'] = positive_signals
        self.results['metrics']['neutral_signals'] = neutral_signals
        self.results['metrics']['firms_with_signals'] = len(sentiment_by_firm)
        
        self.results['details']['sentiment_by_type'] = dict(sentiment_by_type)
        self.results['details']['sentiment_by_source'] = dict(sentiment_by_source)
        
        # Alert on high negative signal rate
        if total_signals > 0:
            negative_rate = (negative_signals / total_signals) * 100
            if negative_rate > 30:
                self.results['alerts'].append(
                    f"High negative sentiment rate: {negative_rate:.1f}% ({negative_signals}/{total_signals})"
                )
        
        logger.info(f"Sentiment detection: {total_signals} signals across {len(sentiment_by_firm)} firms")
    
    def _test_signal_correlation(self):
        """Test if sentiment signals correlate with scores"""
        correlations = {
            'negative_low_score': 0,  # Negative sentiment + low score (good correlation)
            'negative_high_score': 0,  # Negative sentiment + high score (bad correlation)
            'positive_high_score': 0,  # Positive sentiment + high score (good correlation)
            'positive_low_score': 0   # Positive sentiment + low score (bad correlation)
        }
        
        for signal in self.signals:
            firm_id = signal.get('firm_id')
            firm = self.firms_by_id.get(firm_id)
            
            if not firm:
                continue
            
            sentiment = signal.get('sentiment', 'neutral')
            firm_score = firm.get('score_0_100', 50)
            
            if sentiment == 'negative':
                if firm_score < 50:
                    correlations['negative_low_score'] += 1
                else:
                    correlations['negative_high_score'] += 1
                    
                    # Alert on mismatch
                    if firm_score > 70:
                        self.results['alerts'].append(
                            f"Signal mismatch: {firm_id} has negative sentiment but high score ({firm_score})"
                        )
            
            elif sentiment == 'positive':
                if firm_score >= 50:
                    correlations['positive_high_score'] += 1
                else:
                    correlations['positive_low_score'] += 1
        
        # Calculate correlation accuracy
        good_correlations = correlations['negative_low_score'] + correlations['positive_high_score']
        bad_correlations = correlations['negative_high_score'] + correlations['positive_low_score']
        total_correlations = good_correlations + bad_correlations
        
        correlation_accuracy = (good_correlations / total_correlations * 100) if total_correlations > 0 else 0
        
        self.results['metrics']['correlation_accuracy'] = round(correlation_accuracy, 2)
        self.results['details']['correlation_breakdown'] = correlations
        
        if correlation_accuracy < 85:
            self.results['alerts'].append(
                f"Low correlation accuracy: {correlation_accuracy:.1f}% (target: >85%)"
            )
        
        logger.info(f"Signal correlation: {correlation_accuracy:.1f}% accuracy")
    
    def _test_early_warnings(self):
        """Test if soft signals provide early warning before hard data"""
        snapshot_date = self._parse_date(self.metadata.get('generated_at'))
        if snapshot_date and snapshot_date.tzinfo:
            snapshot_date = snapshot_date.replace(tzinfo=None)
        
        if not snapshot_date:
            logger.warning("Snapshot date unavailable - early warning test skipped")
            return
        
        early_warnings = []
        confirmed_warnings = []
        
        for signal in self.signals:
            signal_date = self._parse_date(signal.get('date'))
            
            if not signal_date:
                continue
            
            days_before = (snapshot_date - signal_date).days
            
            # Consider signals from 1-30 days before snapshot
            if 1 <= days_before <= 30:
                firm_id = signal.get('firm_id')
                firm = self.firms_by_id.get(firm_id)
                
                if not firm:
                    continue
                
                sentiment = signal.get('sentiment')
                firm_score = firm.get('score_0_100', 50)
                
                # Early warning if negative sentiment detected before score reflects it
                if sentiment == 'negative':
                    early_warnings.append({
                        'firm_id': firm_id,
                        'firm_name': firm.get('name'),
                        'signal_date': signal.get('date'),
                        'days_before': days_before,
                        'firm_score': firm_score,
                        'source': signal.get('source')
                    })
                    
                    # Confirmed if score is now low
                    if firm_score < 50:
                        confirmed_warnings.append({
                            'firm_id': firm_id,
                            'days_before': days_before
                        })
        
        early_warning_rate = (len(confirmed_warnings) / len(early_warnings) * 100) if early_warnings else 0
        
        self.results['metrics']['early_warnings_detected'] = len(early_warnings)
        self.results['metrics']['early_warnings_confirmed'] = len(confirmed_warnings)
        self.results['metrics']['early_warning_accuracy'] = round(early_warning_rate, 2)
        self.results['details']['early_warnings'] = early_warnings[:5]  # Top 5
        
        logger.info(f"Early warnings: {len(confirmed_warnings)}/{len(early_warnings)} confirmed")
    
    def _test_false_positives(self):
        """Test for false positive rate in sentiment signals"""
        false_positives = []
        true_positives = []
        
        for signal in self.signals:
            firm_id = signal.get('firm_id')
            firm = self.firms_by_id.get(firm_id)
            
            if not firm:
                continue
            
            sentiment = signal.get('sentiment')
            firm_score = firm.get('score_0_100', 50)
            
            # False positive: negative sentiment but firm actually doing well
            if sentiment == 'negative':
                if firm_score >= 70:  # High score despite negative sentiment
                    false_positives.append({
                        'firm_id': firm_id,
                        'firm_name': firm.get('name'),
                        'firm_score': firm_score,
                        'source': signal.get('source'),
                        'text': signal.get('text', '')[:100]
                    })
                else:
                    true_positives.append(firm_id)
        
        total_negatives = len(false_positives) + len(true_positives)
        false_positive_rate = (len(false_positives) / total_negatives * 100) if total_negatives > 0 else 0
        
        self.results['metrics']['false_positive_rate'] = round(false_positive_rate, 2)
        self.results['metrics']['false_positives'] = len(false_positives)
        self.results['details']['false_positive_examples'] = false_positives[:5]  # Top 5
        
        if false_positive_rate > 5:
            self.results['alerts'].append(
                f"High false positive rate: {false_positive_rate:.1f}% (target: <5%)"
            )
        
        logger.info(f"False positive rate: {false_positive_rate:.1f}%")
    
    def _test_multi_source_validation(self):
        """Test if signals are validated across multiple sources"""
        signals_by_firm = defaultdict(list)
        
        for signal in self.signals:
            firm_id = signal.get('firm_id')
            if firm_id:
                signals_by_firm[firm_id].append(signal)
        
        multi_source_firms = 0
        single_source_firms = 0
        
        for firm_id, firm_signals in signals_by_firm.items():
            sources = set(s.get('source') for s in firm_signals)
            
            if len(sources) > 1:
                multi_source_firms += 1
            else:
                single_source_firms += 1
        
        multi_source_rate = (multi_source_firms / len(signals_by_firm) * 100) if signals_by_firm else 0
        
        self.results['metrics']['multi_source_validation_rate'] = round(multi_source_rate, 2)
        self.results['details']['multi_source_analysis'] = {
            'multi_source_firms': multi_source_firms,
            'single_source_firms': single_source_firms
        }
        
        # Higher multi-source rate = more reliable signals
        if multi_source_rate < 30:
            self.results['alerts'].append(
                f"Low multi-source validation: {multi_source_rate:.1f}% (target: >30%)"
            )
        
        logger.info(f"Multi-source validation: {multi_source_rate:.1f}%")
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime object"""
        if not date_str:
            return None
        
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Return timezone-naive for consistent comparison
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt
        except Exception:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                logger.warning(f"Could not parse date: {date_str}")
                return None
    
    def _determine_pass_fail(self):
        """Determine overall test pass/fail based on success criteria"""
        correlation_accuracy = self.results['metrics'].get('correlation_accuracy', 0)
        false_positive_rate = self.results['metrics'].get('false_positive_rate', 100)
        early_warning_accuracy = self.results['metrics'].get('early_warning_accuracy', 0)
        
        # Success criteria:
        # 1. Correlation accuracy > 85%
        # 2. False positive rate < 5%
        # 3. Early warning accuracy > 70%
        
        criteria_met = (
            correlation_accuracy > 85 and
            false_positive_rate < 5 and
            early_warning_accuracy > 70
        )
        
        self.results['passed'] = criteria_met
        self.results['success_criteria'] = {
            'correlation_accuracy_gt_85': correlation_accuracy > 85,
            'false_positive_rate_lt_5': false_positive_rate < 5,
            'early_warning_accuracy_gt_70': early_warning_accuracy > 70
        }


def run_soft_signals_test(
    snapshot_data: Dict[str, Any],
    sentiment_data: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Convenience function to run soft signals test
    
    Args:
        snapshot_data: Complete snapshot dictionary
        sentiment_data: List of sentiment signals
        
    Returns:
        Test results dictionary
    """
    test = SoftSignalsTest(snapshot_data, sentiment_data)
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
        
        # Mock sentiment signals
        mock_signals = [
            {
                "firm_id": "ftmocom",
                "source": "reddit",
                "sentiment": "negative",
                "date": "2026-01-28",
                "text": "FTMO not paying out traders"
            },
            {
                "firm_id": "ftmocom",
                "source": "trustpilot",
                "sentiment": "negative",
                "date": "2026-01-29",
                "text": "Terrible customer service"
            },
            {
                "firm_id": "fundedtradingplus",
                "source": "reddit",
                "sentiment": "positive",
                "date": "2026-01-30",
                "text": "Great experience with FTP"
            }
        ]
        
        results = run_soft_signals_test(snapshot, mock_signals)
        
        print("\n=== Soft Signals Test Results ===")
        print(f"Status: {'✅ PASS' if results['passed'] else '❌ FAIL'}")
        print(f"Total signals: {results['total_signals']}")
        print(f"Correlation accuracy: {results['metrics'].get('correlation_accuracy', 'N/A')}%")
        print(f"False positive rate: {results['metrics'].get('false_positive_rate', 'N/A')}%")
        print(f"Early warnings: {results['metrics'].get('early_warnings_detected', 'N/A')}")
        
        if results['alerts']:
            print("\nAlerts:")
            for alert in results['alerts']:
                print(f"  ⚠️  {alert}")
        
        print("\nSuccess criteria:")
        for criterion, met in results.get('success_criteria', {}).items():
            status = "✅" if met else "❌"
            print(f"  {status} {criterion}")
    else:
        print(f"Test snapshot not found: {snapshot_path}")
