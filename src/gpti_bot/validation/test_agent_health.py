"""
Validation Test 6: Agent Health Monitoring
Created: 2026-02-01
Phase: 1 (Validation Framework) - Week 4

Purpose:
- Monitor data collection agent performance
- Detect stale sources and failures
- Track data freshness and quality by agent
- Alert on degraded agent performance

Success Criteria (v1.1):
- All agents active within 24 hours
- <5% failure rate per agent
- Data freshness <48 hours
- Source quality score >70%

IOSCO Alignment: Article 13 (Methodology Transparency)
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class AgentHealthTest:
    """Test 6: Agent Health Monitoring validation"""
    
    # Expected agents in the system
    EXPECTED_AGENTS = [
        'RVI',  # Registry Verification & Integration
        'SSS',  # Screening & Scoring System
        'REM',  # Regulatory Event Monitor
        'IRS',  # Independent Review System
        'FRP',  # Firm Reputation & Payout tracking
        'MIS',  # Manual Investigation System
        'IIP'   # IOSCO Implementation & Publication
    ]
    
    def __init__(
        self,
        snapshot_data: Dict[str, Any],
        agent_logs: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Initialize agent health test with snapshot and agent logs
        
        Args:
            snapshot_data: Complete snapshot with records and metadata
            agent_logs: List of agent execution logs
        """
        self.snapshot = snapshot_data
        self.records = snapshot_data.get("records", [])
        self.metadata = snapshot_data.get("metadata", {})
        self.agent_logs = agent_logs or []
        self.results = {}
    
    def run(self) -> Dict[str, Any]:
        """
        Execute all agent health monitoring tests
        
        Returns:
            Dictionary with test results and pass/fail status
        """
        logger.info("Running Agent Health Monitoring test...")
        
        self.results = {
            "test_name": "agent_health",
            "timestamp": datetime.utcnow().isoformat(),
            "snapshot_id": self.metadata.get("version", "unknown"),
            "total_agents": len(self.EXPECTED_AGENTS),
            "total_logs": len(self.agent_logs),
            "passed": False,
            "metrics": {},
            "alerts": [],
            "details": {}
        }
        
        if not self.agent_logs:
            logger.warning("No agent logs provided - test limited")
            self.results['alerts'].append("No agent logs available for monitoring")
            self.results['status'] = "LIMITED"
            self._test_from_snapshot_metadata()
            return self.results
        
        # Test 6.1: Agent availability (all agents active)
        self._test_agent_availability()
        
        # Test 6.2: Agent failure rate
        self._test_failure_rate()
        
        # Test 6.3: Data freshness
        self._test_data_freshness()
        
        # Test 6.4: Source quality by agent
        self._test_source_quality()
        
        # Test 6.5: Agent performance trends
        self._test_performance_trends()
        
        # Determine overall pass/fail
        self._determine_pass_fail()
        
        logger.info(f"Agent health test complete: {'PASS' if self.results['passed'] else 'FAIL'}")
        return self.results
    
    def _test_agent_availability(self):
        """Test if all expected agents are active"""
        active_agents = set()
        agent_last_seen = {}
        
        now = datetime.utcnow()
        
        for log in self.agent_logs:
            agent = log.get('agent')
            timestamp = self._parse_date(log.get('timestamp'))
            
            if agent:
                active_agents.add(agent)
                
                if timestamp:
                    if agent not in agent_last_seen or timestamp > agent_last_seen[agent]:
                        agent_last_seen[agent] = timestamp
        
        missing_agents = set(self.EXPECTED_AGENTS) - active_agents
        inactive_agents = []
        
        # Check for agents not seen in 24 hours
        for agent, last_seen in agent_last_seen.items():
            hours_since = (now - last_seen).total_seconds() / 3600
            if hours_since > 24:
                inactive_agents.append({
                    'agent': agent,
                    'last_seen': last_seen.isoformat(),
                    'hours_inactive': round(hours_since, 1)
                })
        
        availability_rate = (len(active_agents) / len(self.EXPECTED_AGENTS) * 100)
        
        self.results['metrics']['agent_availability_rate'] = round(availability_rate, 2)
        self.results['metrics']['active_agents'] = len(active_agents)
        self.results['metrics']['inactive_agents'] = len(inactive_agents)
        self.results['metrics']['missing_agents'] = len(missing_agents)
        
        self.results['details']['active_agent_list'] = sorted(list(active_agents))
        self.results['details']['missing_agent_list'] = sorted(list(missing_agents))
        self.results['details']['inactive_agent_details'] = inactive_agents
        
        # Alerts
        if missing_agents:
            self.results['alerts'].append(
                f"Missing agents: {', '.join(sorted(missing_agents))}"
            )
        
        if inactive_agents:
            self.results['alerts'].append(
                f"{len(inactive_agents)} agents inactive >24h"
            )
        
        logger.info(f"Agent availability: {len(active_agents)}/{len(self.EXPECTED_AGENTS)} = {availability_rate:.1f}%")
    
    def _test_failure_rate(self):
        """Test agent failure rates"""
        agent_stats = defaultdict(lambda: {'total': 0, 'failures': 0, 'successes': 0})
        
        for log in self.agent_logs:
            agent = log.get('agent')
            status = log.get('status', 'unknown')
            
            if agent:
                agent_stats[agent]['total'] += 1
                
                if status in ['failure', 'error', 'failed']:
                    agent_stats[agent]['failures'] += 1
                elif status in ['success', 'completed']:
                    agent_stats[agent]['successes'] += 1
        
        # Calculate failure rates
        agent_failure_rates = {}
        high_failure_agents = []
        
        for agent, stats in agent_stats.items():
            if stats['total'] > 0:
                failure_rate = (stats['failures'] / stats['total']) * 100
                agent_failure_rates[agent] = {
                    'failure_rate': round(failure_rate, 2),
                    'total_runs': stats['total'],
                    'failures': stats['failures'],
                    'successes': stats['successes']
                }
                
                if failure_rate > 5:
                    high_failure_agents.append({
                        'agent': agent,
                        'failure_rate': round(failure_rate, 2)
                    })
        
        # Overall failure rate
        total_runs = sum(s['total'] for s in agent_stats.values())
        total_failures = sum(s['failures'] for s in agent_stats.values())
        overall_failure_rate = (total_failures / total_runs * 100) if total_runs > 0 else 0
        
        self.results['metrics']['overall_failure_rate'] = round(overall_failure_rate, 2)
        self.results['metrics']['total_agent_runs'] = total_runs
        self.results['metrics']['total_failures'] = total_failures
        
        self.results['details']['agent_failure_rates'] = agent_failure_rates
        self.results['details']['high_failure_agents'] = high_failure_agents
        
        # Alerts
        if overall_failure_rate > 5:
            self.results['alerts'].append(
                f"High overall failure rate: {overall_failure_rate:.1f}% (target: <5%)"
            )
        
        for agent_info in high_failure_agents:
            self.results['alerts'].append(
                f"High failure rate for {agent_info['agent']}: {agent_info['failure_rate']}%"
            )
        
        logger.info(f"Failure rate: {overall_failure_rate:.1f}% across {total_runs} runs")
    
    def _test_data_freshness(self):
        """Test data freshness by agent"""
        now = datetime.utcnow()
        agent_freshness = defaultdict(list)
        
        for log in self.agent_logs:
            agent = log.get('agent')
            timestamp = self._parse_date(log.get('timestamp'))
            
            if agent and timestamp:
                hours_old = (now - timestamp).total_seconds() / 3600
                agent_freshness[agent].append(hours_old)
        
        # Calculate average freshness per agent
        agent_avg_freshness = {}
        stale_agents = []
        
        for agent, freshness_list in agent_freshness.items():
            if freshness_list:
                avg_freshness = sum(freshness_list) / len(freshness_list)
                agent_avg_freshness[agent] = round(avg_freshness, 1)
                
                if avg_freshness > 48:  # More than 48 hours old
                    stale_agents.append({
                        'agent': agent,
                        'avg_age_hours': round(avg_freshness, 1)
                    })
        
        # Overall freshness
        all_freshness = [h for hours_list in agent_freshness.values() for h in hours_list]
        avg_overall_freshness = (sum(all_freshness) / len(all_freshness)) if all_freshness else 999
        
        self.results['metrics']['avg_data_freshness_hours'] = round(avg_overall_freshness, 1)
        self.results['metrics']['stale_agents'] = len(stale_agents)
        
        self.results['details']['agent_freshness'] = agent_avg_freshness
        self.results['details']['stale_agent_details'] = stale_agents
        
        # Alerts
        if avg_overall_freshness > 48:
            self.results['alerts'].append(
                f"Data staleness issue: avg {avg_overall_freshness:.1f}h old (target: <48h)"
            )
        
        for agent_info in stale_agents:
            self.results['alerts'].append(
                f"Stale data from {agent_info['agent']}: {agent_info['avg_age_hours']}h old"
            )
        
        logger.info(f"Data freshness: {avg_overall_freshness:.1f}h average age")
    
    def _test_source_quality(self):
        """Test source quality by agent"""
        agent_quality = defaultdict(lambda: {'total': 0, 'quality_sum': 0})
        
        for log in self.agent_logs:
            agent = log.get('agent')
            quality = log.get('quality_score')  # 0-100
            
            if agent and quality is not None:
                agent_quality[agent]['total'] += 1
                agent_quality[agent]['quality_sum'] += quality
        
        # Calculate average quality per agent
        agent_avg_quality = {}
        low_quality_agents = []
        
        for agent, stats in agent_quality.items():
            if stats['total'] > 0:
                avg_quality = stats['quality_sum'] / stats['total']
                agent_avg_quality[agent] = round(avg_quality, 1)
                
                if avg_quality < 70:
                    low_quality_agents.append({
                        'agent': agent,
                        'avg_quality': round(avg_quality, 1)
                    })
        
        # Overall quality
        total_quality_samples = sum(s['total'] for s in agent_quality.values())
        total_quality_sum = sum(s['quality_sum'] for s in agent_quality.values())
        avg_overall_quality = (total_quality_sum / total_quality_samples) if total_quality_samples > 0 else 0
        
        self.results['metrics']['avg_source_quality'] = round(avg_overall_quality, 1)
        self.results['metrics']['low_quality_agents'] = len(low_quality_agents)
        
        self.results['details']['agent_quality_scores'] = agent_avg_quality
        self.results['details']['low_quality_agent_details'] = low_quality_agents
        
        # Alerts
        if avg_overall_quality < 70:
            self.results['alerts'].append(
                f"Low source quality: {avg_overall_quality:.1f}/100 (target: >70)"
            )
        
        for agent_info in low_quality_agents:
            self.results['alerts'].append(
                f"Low quality from {agent_info['agent']}: {agent_info['avg_quality']}/100"
            )
        
        logger.info(f"Source quality: {avg_overall_quality:.1f}/100 average")
    
    def _test_performance_trends(self):
        """Test agent performance trends over time"""
        # Group logs by day
        logs_by_day = defaultdict(lambda: defaultdict(list))
        
        for log in self.agent_logs:
            agent = log.get('agent')
            timestamp = self._parse_date(log.get('timestamp'))
            status = log.get('status')
            
            if agent and timestamp:
                day = timestamp.date().isoformat()
                logs_by_day[day][agent].append(status)
        
        # Detect degrading agents (failure rate increasing over time)
        degrading_agents = []
        
        sorted_days = sorted(logs_by_day.keys())
        if len(sorted_days) >= 2:
            recent_day = sorted_days[-1]
            previous_day = sorted_days[-2]
            
            for agent in self.EXPECTED_AGENTS:
                recent_runs = logs_by_day[recent_day].get(agent, [])
                previous_runs = logs_by_day[previous_day].get(agent, [])
                
                if recent_runs and previous_runs:
                    recent_failures = sum(1 for s in recent_runs if s in ['failure', 'error'])
                    previous_failures = sum(1 for s in previous_runs if s in ['failure', 'error'])
                    
                    recent_rate = (recent_failures / len(recent_runs)) * 100
                    previous_rate = (previous_failures / len(previous_runs)) * 100
                    
                    if recent_rate > previous_rate + 10:  # 10% increase
                        degrading_agents.append({
                            'agent': agent,
                            'previous_failure_rate': round(previous_rate, 1),
                            'recent_failure_rate': round(recent_rate, 1)
                        })
        
        self.results['metrics']['degrading_agents'] = len(degrading_agents)
        self.results['details']['degrading_agent_details'] = degrading_agents
        
        # Alerts
        for agent_info in degrading_agents:
            self.results['alerts'].append(
                f"Degrading performance: {agent_info['agent']} "
                f"({agent_info['previous_failure_rate']}% → {agent_info['recent_failure_rate']}%)"
            )
        
        logger.info(f"Performance trends: {len(degrading_agents)} agents degrading")
    
    def _test_from_snapshot_metadata(self):
        """Fallback test using only snapshot metadata"""
        logger.info("Running limited agent health test from snapshot metadata")
        
        # Check if snapshot has agent metadata
        agents_used = self.metadata.get('agents_used', [])
        
        if agents_used:
            self.results['metrics']['agents_in_snapshot'] = len(agents_used)
            self.results['details']['agents_used'] = agents_used
            
            missing = set(self.EXPECTED_AGENTS) - set(agents_used)
            if missing:
                self.results['alerts'].append(
                    f"Agents not used in snapshot: {', '.join(sorted(missing))}"
                )
        else:
            self.results['alerts'].append(
                "No agent metadata available in snapshot"
            )
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime object"""
        if not date_str:
            return None
        
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt
        except Exception:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                logger.warning(f"Could not parse date: {date_str}")
                return None
    
    def _determine_pass_fail(self):
        """Determine overall test pass/fail based on success criteria"""
        availability_rate = self.results['metrics'].get('agent_availability_rate', 0)
        failure_rate = self.results['metrics'].get('overall_failure_rate', 100)
        freshness_hours = self.results['metrics'].get('avg_data_freshness_hours', 999)
        quality_score = self.results['metrics'].get('avg_source_quality', 0)
        
        # Success criteria:
        # 1. Agent availability > 95%
        # 2. Failure rate < 5%
        # 3. Data freshness < 48 hours
        # 4. Source quality > 70
        
        criteria_met = (
            availability_rate > 95 and
            failure_rate < 5 and
            freshness_hours < 48 and
            quality_score > 70
        )
        
        self.results['passed'] = criteria_met
        self.results['success_criteria'] = {
            'availability_gt_95': availability_rate > 95,
            'failure_rate_lt_5': failure_rate < 5,
            'freshness_lt_48h': freshness_hours < 48,
            'quality_gt_70': quality_score > 70
        }


def run_agent_health_test(
    snapshot_data: Dict[str, Any],
    agent_logs: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Convenience function to run agent health test
    
    Args:
        snapshot_data: Complete snapshot dictionary
        agent_logs: List of agent execution logs
        
    Returns:
        Test results dictionary
    """
    test = AgentHealthTest(snapshot_data, agent_logs)
    return test.run()


# Example usage
if __name__ == "__main__":
    import json
    from pathlib import Path
    from datetime import datetime, timedelta
    
    # Load test snapshot
    snapshot_path = Path("/opt/gpti/gpti-site/data/test-snapshot.json")
    
    if snapshot_path.exists():
        with open(snapshot_path) as f:
            snapshot = json.load(f)
        
        # Mock agent logs
        now = datetime.utcnow()
        mock_logs = []
        
        agents = ['RVI', 'SSS', 'REM', 'IRS', 'FRP']
        for i in range(50):
            agent = agents[i % len(agents)]
            timestamp = (now - timedelta(hours=i * 0.5)).isoformat()
            
            mock_logs.append({
                'agent': agent,
                'timestamp': timestamp,
                'status': 'success' if i % 10 != 0 else 'failure',
                'quality_score': 85 - (i % 20)
            })
        
        results = run_agent_health_test(snapshot, mock_logs)
        
        print("\n=== Agent Health Test Results ===")
        print(f"Status: {'✅ PASS' if results['passed'] else '❌ FAIL'}")
        print(f"Total agents: {results['total_agents']}")
        print(f"Availability: {results['metrics'].get('agent_availability_rate', 'N/A')}%")
        print(f"Failure rate: {results['metrics'].get('overall_failure_rate', 'N/A')}%")
        print(f"Data freshness: {results['metrics'].get('avg_data_freshness_hours', 'N/A')}h")
        print(f"Source quality: {results['metrics'].get('avg_source_quality', 'N/A')}/100")
        
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
