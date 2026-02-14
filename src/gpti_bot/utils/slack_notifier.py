"""
Slack Notifier - Alert system for validation failures and critical events
Created: 2026-02-01
Phase: 1 (Validation Framework)

Purpose:
- Send alerts to Slack channel when validation metrics fail thresholds
- Notify team of critical events (regulatory actions, score anomalies)
- Daily summary reports for validation dashboard

Configuration:
Set environment variable: SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

Usage:
    from gpti_bot.utils.slack_notifier import SlackNotifier
    
    notifier = SlackNotifier()
    notifier.send_alert("High NA rate detected: 35%", severity="warning")
    notifier.send_validation_summary(metrics)
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None  # type: ignore

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Send alerts and reports to Slack"""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize Slack notifier
        
        Args:
            webhook_url: Slack webhook URL (defaults to SLACK_WEBHOOK_URL env var)
        """
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.enabled = bool(self.webhook_url and requests)
        
        if not self.enabled:
            if not self.webhook_url:
                logger.warning("SLACK_WEBHOOK_URL not configured - notifications disabled")
            if not requests:
                logger.warning("requests library not installed - notifications disabled")
    
    def send_alert(
        self, 
        message: str, 
        severity: str = "info",
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send a simple alert to Slack
        
        Args:
            message: Alert message
            severity: Alert level (info, warning, error, critical)
            details: Optional additional details dictionary
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug(f"Slack disabled - would send: [{severity}] {message}")
            return False
        
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "🚨",
            "critical": "🔥"
        }
        
        emoji = emoji_map.get(severity, "📢")
        
        payload = {
            "text": f"{emoji} *{severity.upper()}* - {message}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *{severity.upper()}*\n{message}"
                    }
                }
            ]
        }
        
        if details:
            details_text = "\n".join([f"• *{k}*: {v}" for k, v in details.items()])
            payload["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Details:*\n{details_text}"
                }
            })
        
        payload["blocks"].append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"GPTI Validation System | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            }]
        })
        
        return self._send_to_slack(payload)
    
    def send_validation_summary(self, metrics: Dict[str, Any]) -> bool:
        """
        Send daily validation summary report
        
        Args:
            metrics: Validation metrics dictionary from validation framework
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug("Slack disabled - would send validation summary")
            return False
        
        coverage = metrics.get("coverage", {})
        stability = metrics.get("stability", {})
        ground_truth = metrics.get("ground_truth", {})
        alerts = metrics.get("alerts", [])
        
        # Build status message
        status_icon = "✅" if not alerts else "⚠️"
        status_text = "All systems nominal" if not alerts else f"{len(alerts)} alert(s)"
        
        payload = {
            "text": f"{status_icon} Validation Summary - {status_text}",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{status_icon} Daily Validation Summary"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Snapshot ID:*\n{metrics.get('snapshot_id', 'N/A')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Timestamp:*\n{metrics.get('timestamp', 'N/A')}"
                        }
                    ]
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Coverage & Data Sufficiency*"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Total Firms:* {coverage.get('total_firms', 0)}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Coverage:* {coverage.get('coverage_percent', 0)}%"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Avg NA Rate:* {coverage.get('avg_na_rate', 0)}%"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Pass Rate:* {coverage.get('agent_c_pass_rate', 0)}%"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Stability*"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Avg Change:* {stability.get('avg_score_change', 0):.4f}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Top 10 Turnover:* {stability.get('top_10_turnover', 0)}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Ground Truth*"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Events:* {ground_truth.get('events_in_period', 0)}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Precision:* {ground_truth.get('prediction_precision', 0)}%"
                        }
                    ]
                }
            ]
        }
        
        # Add alerts section if any
        if alerts:
            alert_text = "\n".join([f"• {alert}" for alert in alerts])
            payload["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*⚠️ Active Alerts:*\n{alert_text}"
                }
            })
        
        payload["blocks"].append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"GPTI Validation Dashboard | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            }]
        })
        
        return self._send_to_slack(payload)
    
    def send_ground_truth_event(self, event: Dict[str, Any]) -> bool:
        """
        Send notification about new ground-truth event
        
        Args:
            event: Ground truth event dictionary
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug("Slack disabled - would send ground truth event")
            return False
        
        severity_emoji = {
            "critical": "🔥",
            "high": "🚨",
            "medium": "⚠️",
            "low": "ℹ️"
        }
        
        emoji = severity_emoji.get(event.get("event_severity", "medium"), "📢")
        
        payload = {
            "text": f"{emoji} Ground Truth Event: {event.get('event_type')}",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} New Ground Truth Event"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Firm:* {event.get('firm_id')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Type:* {event.get('event_type')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Severity:* {event.get('event_severity')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Date:* {event.get('event_date')}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Description:*\n{event.get('event_description')}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Source:* {event.get('source_type')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Reliability:* {event.get('source_reliability')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Expected Impact:* {event.get('expected_score_impact', 0)}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Direction:* {event.get('expected_direction', 'N/A')}"
                        }
                    ]
                }
            ]
        }
        
        if event.get("source_url"):
            payload["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{event['source_url']}|View Source>"
                }
            })
        
        return self._send_to_slack(payload)
    
    def _send_to_slack(self, payload: Dict[str, Any]) -> bool:
        """
        Internal method to send payload to Slack webhook
        
        Args:
            payload: Slack message payload
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not requests:
            return False
        
        try:
            response = requests.post(
                self.webhook_url,  # type: ignore
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info("Slack notification sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False


# TODO: Integration with Prefect flows
# Example usage in validation flow:
"""
from gpti_bot.utils.slack_notifier import SlackNotifier

notifier = SlackNotifier()

# In validation flow after metrics calculation:
if metrics["coverage"]["avg_na_rate"] > 25:
    notifier.send_alert(
        f"High NA rate detected: {metrics['coverage']['avg_na_rate']}%",
        severity="warning",
        details={
            "Total Firms": metrics["coverage"]["total_firms"],
            "Snapshot": metrics["snapshot_id"]
        }
    )

# Daily summary (scheduled task):
notifier.send_validation_summary(metrics)
"""
