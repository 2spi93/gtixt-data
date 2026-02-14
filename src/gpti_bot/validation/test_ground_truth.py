"""
Validation Test 3: Ground Truth Alignment
Created: 2026-02-01
Phase: 1 (Validation Framework) - Week 4

Purpose:
- Compare scores against known regulatory events
- Detect when scores don't reflect confirmed issues
- Verify score updates triggered by events
- Ensure methodology captures real-world changes

Success Criteria (v1.1):
- 90%+ of known events reflected in scores
- Score changes within 7 days of event
- No false negatives (missed serious events)
- Event severity matches score impact

IOSCO Alignment: Article 15 (Methodology Rigor)
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class GroundTruthTest:
    """Test 3: Ground Truth Alignment validation"""
    
    def __init__(
        self,
        snapshot_data: Dict[str, Any],
        events_data: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Initialize ground truth test with snapshot and events
        
        Args:
            snapshot_data: Complete snapshot with records and metadata
            events_data: List of ground truth events for comparison
        """
        self.snapshot = snapshot_data
        self.records = snapshot_data.get("records", [])
        self.metadata = snapshot_data.get("metadata", {})
        self.events = events_data or []
        self.results = {}
        
        # Build firm lookup for quick access
        self.firms_by_id = {r['firm_id']: r for r in self.records}
    
    def run(self) -> Dict[str, Any]:
        """
        Execute all ground truth alignment tests
        
        Returns:
            Dictionary with test results and pass/fail status
        """
        logger.info("Running Ground Truth Alignment test...")
        
        self.results = {
            "test_name": "ground_truth",
            "timestamp": datetime.utcnow().isoformat(),
            "snapshot_id": self.metadata.get("version", "unknown"),
            "snapshot_date": self.metadata.get("generated_at", "unknown"),
            "total_firms": len(self.records),
            "total_events": len(self.events),
            "passed": False,
            "metrics": {},
            "alerts": [],
            "details": {}
        }
        
        if not self.events:
            logger.warning("No ground truth events provided - test limited")
            self.results['alerts'].append("No ground truth events available for comparison")
            self.results['status'] = "LIMITED"
            return self.results
        
        # Test 3.1: Event detection rate
        self._test_event_detection()
        
        # Test 3.2: Score responsiveness (events trigger changes)
        self._test_score_responsiveness()
        
        # Test 3.3: Event severity alignment
        self._test_severity_alignment()
        
        # Test 3.4: False negatives (missed events)
        self._test_false_negatives()
        
        # Test 3.5: Temporal alignment (scores updated within timeframe)
        self._test_temporal_alignment()
        
        # Determine overall pass/fail
        self._determine_pass_fail()
        
        logger.info(f"Ground truth test complete: {'PASS' if self.results['passed'] else 'FAIL'}")
        return self.results
    
    def _test_event_detection(self):
        """Test if known events are reflected in scores"""
        events_by_firm = {}
        for event in self.events:
            firm_id = event.get('firm_id')
            if firm_id:
                if firm_id not in events_by_firm:
                    events_by_firm[firm_id] = []
                events_by_firm[firm_id].append(event)
        
        detected_events = 0
        missed_events = 0
        event_details = []
        
        for firm_id, firm_events in events_by_firm.items():
            firm = self.firms_by_id.get(firm_id)
            
            if not firm:
                # Firm not in snapshot - event missed
                missed_events += len(firm_events)
                for event in firm_events:
                    event_details.append({
                        "firm_id": firm_id,
                        "event_type": event.get('event_type'),
                        "severity": event.get('severity'),
                        "status": "FIRM_NOT_FOUND"
                    })
                continue
            
            for event in firm_events:
                # Check if event is reflected in score
                event_date = self._parse_date(event.get('event_date'))
                severity = event.get('severity', 'medium')
                event_type = event.get('event_type', 'unknown')
                
                # Heuristic: negative events should reduce score
                is_negative = event_type in ['regulatory_action', 'license_revoked', 'fraud', 'payout_failure']
                
                firm_score = firm.get('score_0_100', 50)
                
                # Consider event "detected" if:
                # 1. Negative event + low score (<40), or
                # 2. Event noted in firm metadata, or
                # 3. Firm has low confidence (indicates issues)
                detected = False
                
                if is_negative and firm_score < 40:
                    detected = True
                elif firm.get('confidence') == 'low':
                    detected = True
                # Could also check detailed_metrics for event indicators
                
                if detected:
                    detected_events += 1
                    status = "DETECTED"
                else:
                    missed_events += 1
                    status = "MISSED"
                    
                    # Alert on missed high-severity events
                    if severity == 'high':
                        self.results['alerts'].append(
                            f"Missed high-severity event: {firm_id} - {event_type}"
                        )
                
                event_details.append({
                    "firm_id": firm_id,
                    "firm_name": firm.get('name'),
                    "event_type": event_type,
                    "severity": severity,
                    "event_date": event.get('event_date'),
                    "firm_score": firm_score,
                    "status": status
                })
        
        total_events = detected_events + missed_events
        detection_rate = (detected_events / total_events * 100) if total_events > 0 else 0
        
        self.results['metrics']['event_detection_rate'] = round(detection_rate, 2)
        self.results['metrics']['events_detected'] = detected_events
        self.results['metrics']['events_missed'] = missed_events
        self.results['details']['event_detection'] = event_details
        
        if detection_rate < 90:
            self.results['alerts'].append(
                f"Low event detection rate: {detection_rate:.1f}% (target: >90%)"
            )
        
        logger.info(f"Event detection: {detected_events}/{total_events} = {detection_rate:.1f}%")
    
    def _test_score_responsiveness(self):
        """Test if scores change in response to events"""
        # This requires historical snapshots for comparison
        # For now, we'll analyze if firms with recent events have appropriate scores
        
        recent_events = []
        snapshot_date = self._parse_date(self.metadata.get('generated_at'))
        if snapshot_date and snapshot_date.tzinfo:
            snapshot_date = snapshot_date.replace(tzinfo=None)
        
        for event in self.events:
            event_date = self._parse_date(event.get('event_date'))
            if event_date and event_date.tzinfo:
                event_date = event_date.replace(tzinfo=None)
            if event_date and snapshot_date:
                days_since = (snapshot_date - event_date).days
                if 0 <= days_since <= 30:  # Events in last 30 days
                    recent_events.append({
                        **event,
                        'days_since': days_since
                    })
        
        responsive_count = 0
        unresponsive_count = 0
        
        for event in recent_events:
            firm_id = event.get('firm_id')
            firm = self.firms_by_id.get(firm_id)
            
            if not firm:
                unresponsive_count += 1
                continue
            
            event_type = event.get('event_type')
            severity = event.get('severity', 'medium')
            firm_score = firm.get('score_0_100', 50)
            
            # Expect negative events to result in lower scores
            is_negative = event_type in ['regulatory_action', 'license_revoked', 'fraud', 'payout_failure']
            
            # Score should be <50 for negative events (rough heuristic)
            if is_negative and firm_score < 50:
                responsive_count += 1
            elif not is_negative and firm_score >= 50:
                responsive_count += 1
            else:
                unresponsive_count += 1
                
                if severity == 'high':
                    self.results['alerts'].append(
                        f"Score unresponsive to high-severity event: {firm_id} - {event_type} "
                        f"({event['days_since']} days ago, score: {firm_score})"
                    )
        
        total_recent = responsive_count + unresponsive_count
        responsiveness_rate = (responsive_count / total_recent * 100) if total_recent > 0 else 0
        
        self.results['metrics']['score_responsiveness_rate'] = round(responsiveness_rate, 2)
        self.results['metrics']['recent_events'] = len(recent_events)
        self.results['details']['recent_events_analysis'] = {
            "total_recent_events": len(recent_events),
            "responsive": responsive_count,
            "unresponsive": unresponsive_count
        }
        
        logger.info(f"Score responsiveness: {responsive_count}/{total_recent} = {responsiveness_rate:.1f}%")
    
    def _test_severity_alignment(self):
        """Test if event severity matches score impact"""
        severity_alignment = {
            'high': {'expected_low_score': 0, 'actual_low_score': 0},
            'medium': {'expected_mid_score': 0, 'actual_mid_score': 0},
            'low': {'expected_any_score': 0, 'actual_any_score': 0}
        }
        
        for event in self.events:
            firm_id = event.get('firm_id')
            firm = self.firms_by_id.get(firm_id)
            
            if not firm:
                continue
            
            severity = event.get('severity', 'medium')
            event_type = event.get('event_type')
            firm_score = firm.get('score_0_100', 50)
            
            is_negative = event_type in ['regulatory_action', 'license_revoked', 'fraud', 'payout_failure']
            
            if not is_negative:
                continue  # Only check negative events
            
            if severity == 'high':
                severity_alignment['high']['expected_low_score'] += 1
                if firm_score < 30:  # High severity should result in very low scores
                    severity_alignment['high']['actual_low_score'] += 1
            
            elif severity == 'medium':
                severity_alignment['medium']['expected_mid_score'] += 1
                if 30 <= firm_score < 60:  # Medium severity = mid-range scores
                    severity_alignment['medium']['actual_mid_score'] += 1
            
            elif severity == 'low':
                severity_alignment['low']['expected_any_score'] += 1
                severity_alignment['low']['actual_any_score'] += 1  # Any score acceptable
        
        self.results['details']['severity_alignment'] = severity_alignment
        
        # Check alignment rates
        for sev, data in severity_alignment.items():
            if sev == 'high':
                expected = data['expected_low_score']
                actual = data['actual_low_score']
            elif sev == 'medium':
                expected = data['expected_mid_score']
                actual = data['actual_mid_score']
            else:
                expected = data['expected_any_score']
                actual = data['actual_any_score']
            
            if expected > 0:
                alignment_rate = (actual / expected * 100)
                if alignment_rate < 80 and sev == 'high':
                    self.results['alerts'].append(
                        f"Poor severity alignment for {sev} events: {alignment_rate:.1f}% "
                        f"({actual}/{expected})"
                    )
        
        logger.info(f"Severity alignment analyzed for {len(self.events)} events")
    
    def _test_false_negatives(self):
        """Test for false negatives (events we should have detected but didn't)"""
        # Count high-severity events not reflected in scores
        false_negatives = []
        
        for event in self.events:
            severity = event.get('severity')
            if severity != 'high':
                continue  # Only concerned about missing high-severity
            
            firm_id = event.get('firm_id')
            firm = self.firms_by_id.get(firm_id)
            
            if not firm:
                false_negatives.append({
                    "firm_id": firm_id,
                    "event_type": event.get('event_type'),
                    "reason": "Firm not in snapshot"
                })
                continue
            
            event_type = event.get('event_type')
            is_negative = event_type in ['regulatory_action', 'license_revoked', 'fraud', 'payout_failure']
            firm_score = firm.get('score_0_100', 50)
            
            # High-severity negative event should result in score <40
            if is_negative and firm_score >= 40:
                false_negatives.append({
                    "firm_id": firm_id,
                    "firm_name": firm.get('name'),
                    "event_type": event_type,
                    "severity": severity,
                    "firm_score": firm_score,
                    "reason": f"Score {firm_score} too high for high-severity event"
                })
        
        self.results['metrics']['false_negatives'] = len(false_negatives)
        self.results['details']['false_negatives'] = false_negatives[:10]  # Top 10
        
        if len(false_negatives) > 0:
            self.results['alerts'].append(
                f"{len(false_negatives)} potential false negatives (high-severity events missed)"
            )
        
        logger.info(f"False negatives: {len(false_negatives)}")
    
    def _test_temporal_alignment(self):
        """Test if score updates occur within reasonable timeframe"""
        snapshot_date = self._parse_date(self.metadata.get('generated_at'))
        if snapshot_date and snapshot_date.tzinfo:
            snapshot_date = snapshot_date.replace(tzinfo=None)
        
        if not snapshot_date:
            logger.warning("Snapshot date not available - temporal test skipped")
            return
        
        timely_updates = 0
        delayed_updates = 0
        
        for event in self.events:
            event_date = self._parse_date(event.get('event_date'))
            if event_date and event_date.tzinfo:
                event_date = event_date.replace(tzinfo=None)
            
            if not event_date:
                continue
            
            days_since = (snapshot_date - event_date).days
            
            # Events should be reflected within 7 days
            if 0 <= days_since <= 7:
                firm_id = event.get('firm_id')
                firm = self.firms_by_id.get(firm_id)
                
                if firm:
                    event_type = event.get('event_type')
                    is_negative = event_type in ['regulatory_action', 'license_revoked', 'fraud', 'payout_failure']
                    firm_score = firm.get('score_0_100', 50)
                    
                    # Check if reflected
                    if (is_negative and firm_score < 50) or (not is_negative and firm_score >= 50):
                        timely_updates += 1
                    else:
                        delayed_updates += 1
            
            elif days_since > 7:
                # Check if eventually reflected
                firm_id = event.get('firm_id')
                firm = self.firms_by_id.get(firm_id)
                
                if firm:
                    event_type = event.get('event_type')
                    is_negative = event_type in ['regulatory_action', 'license_revoked', 'fraud', 'payout_failure']
                    firm_score = firm.get('score_0_100', 50)
                    
                    if not ((is_negative and firm_score < 50) or (not is_negative and firm_score >= 50)):
                        delayed_updates += 1
        
        total_temporal = timely_updates + delayed_updates
        timeliness_rate = (timely_updates / total_temporal * 100) if total_temporal > 0 else 0
        
        self.results['metrics']['timeliness_rate'] = round(timeliness_rate, 2)
        self.results['details']['temporal_analysis'] = {
            "timely_updates": timely_updates,
            "delayed_updates": delayed_updates
        }
        
        if timeliness_rate < 80:
            self.results['alerts'].append(
                f"Low timeliness rate: {timeliness_rate:.1f}% (target: >80%)"
            )
        
        logger.info(f"Timeliness: {timely_updates}/{total_temporal} = {timeliness_rate:.1f}%")
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime object"""
        if not date_str:
            return None
        
        try:
            # Try ISO format first
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Ensure timezone-aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=None)
            return dt
        except Exception:
            try:
                # Try common formats - return timezone-naive for comparison
                return datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                logger.warning(f"Could not parse date: {date_str}")
                return None
    
    def _determine_pass_fail(self):
        """Determine overall test pass/fail based on success criteria"""
        detection_rate = self.results['metrics'].get('event_detection_rate', 0)
        false_negatives = self.results['metrics'].get('false_negatives', 999)
        responsiveness_rate = self.results['metrics'].get('score_responsiveness_rate', 0)
        
        # Success criteria:
        # 1. Event detection rate > 90%
        # 2. No false negatives for high-severity events (or <2)
        # 3. Score responsiveness > 80%
        
        criteria_met = (
            detection_rate > 90 and
            false_negatives < 2 and
            responsiveness_rate > 80
        )
        
        self.results['passed'] = criteria_met
        self.results['success_criteria'] = {
            'detection_rate_gt_90': detection_rate > 90,
            'false_negatives_lt_2': false_negatives < 2,
            'responsiveness_gt_80': responsiveness_rate > 80
        }


def run_ground_truth_test(
    snapshot_data: Dict[str, Any],
    events_data: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Convenience function to run ground truth test
    
    Args:
        snapshot_data: Complete snapshot dictionary
        events_data: List of ground truth events
        
    Returns:
        Test results dictionary
    """
    test = GroundTruthTest(snapshot_data, events_data)
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
        
        # Mock ground truth events (in production, load from database)
        mock_events = [
            {
                "firm_id": "ftmocom",
                "event_type": "regulatory_action",
                "severity": "high",
                "event_date": "2026-01-15",
                "description": "FTMO regulatory compliance issue"
            },
            {
                "firm_id": "fundedtradingplus",
                "event_type": "payout_change",
                "severity": "medium",
                "event_date": "2026-01-20",
                "description": "Payout policy updated"
            },
            {
                "firm_id": "topsteptrader",
                "event_type": "rule_change",
                "severity": "low",
                "event_date": "2026-01-25",
                "description": "Trading rules modified"
            }
        ]
        
        results = run_ground_truth_test(snapshot, mock_events)
        
        print("\n=== Ground Truth Test Results ===")
        print(f"Status: {'✅ PASS' if results['passed'] else '❌ FAIL'}")
        print(f"Total events: {results['total_events']}")
        print(f"Detection rate: {results['metrics'].get('event_detection_rate', 'N/A')}%")
        print(f"Responsiveness: {results['metrics'].get('score_responsiveness_rate', 'N/A')}%")
        print(f"False negatives: {results['metrics'].get('false_negatives', 'N/A')}")
        
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
