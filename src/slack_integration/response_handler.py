"""Slack response formatter and sender."""

import logging
from typing import Dict, Any
from slack_sdk import WebClient
from datetime import datetime

logger = logging.getLogger(__name__)


class ResponseHandler:
    """Format and send responses to Slack."""

    def __init__(self, client: WebClient):
        """Initialize response handler."""
        self.client = client

    def send_response(
        self, channel: str, response: Dict[str, Any], thread_ts: str
    ):
        """Send formatted response to Slack channel."""
        try:
            if response.get("success"):
                message = self._format_success_response(response)
            else:
                message = self._format_error_response(response)

            self.client.chat_postMessage(
                channel=channel,
                blocks=message["blocks"],
                text=message["text"],
                thread_ts=thread_ts,
            )

            # Log interaction
            self._log_interaction(response)

        except Exception as e:
            logger.error(f"Error sending response: {e}")
            try:
                self.client.chat_postMessage(
                    channel=channel,
                    text=f"❌ Erreur lors de l'envoi: {str(e)}",
                    thread_ts=thread_ts,
                )
            except:
                pass

    def _format_success_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Format successful agent response."""
        agent = response.get("agent", "?")
        query = response.get("query", "")
        agent_response = response.get("response", "Pas de réponse")
        sources = response.get("sources", [])
        execution_time = response.get("execution_time", "0s")
        data_available = response.get("data_context_available", False)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🤖 Agent {agent}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Question:*\n{query}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Réponse:*\n{agent_response}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📊 Sources: {', '.join(sources) if sources else 'N/A'} | ⏱️ {execution_time} | 📦 Snapshots: {'✅' if data_available else '❌'}",
                    }
                ],
            },
        ]

        return {
            "blocks": blocks,
            "text": f"Agent {agent} response: {agent_response[:100]}...",
        }

    def _format_error_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Format error response."""
        error_msg = response.get("response", "Erreur inconnue")

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"❌ *Erreur*\n{error_msg}",
                },
            },
        ]

        return {
            "blocks": blocks,
            "text": f"Error: {error_msg}",
        }

    def _log_interaction(self, response: Dict[str, Any]):
        """Log interaction to database/file."""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "success": response.get("success"),
                "agent": response.get("agent"),
                "query": response.get("query"),
                "user_id": response.get("user_id"),
                "execution_time": response.get("execution_time"),
            }

            logger.info(f"Slack interaction: {log_entry}")

            # Could be extended to save to database for audit trail
            # db.save_slack_interaction(log_entry)

        except Exception as e:
            logger.error(f"Error logging interaction: {e}")
