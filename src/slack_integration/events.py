"""Slack event handler for message processing."""

import os
import json
import logging
from typing import Optional, Dict, Any
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk import WebClient

logger = logging.getLogger(__name__)


class SlackEventHandler:
    """Handle Slack events and route to agents."""

    def __init__(self):
        """Initialize Slack app and client."""
        self.app = App(
            token=os.getenv("SLACK_BOT_TOKEN"),
            signing_secret=os.getenv("SLACK_SIGNING_SECRET"),
        )
        self.client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
        self._register_handlers()

    def _register_handlers(self):
        """Register event handlers."""
        # Message handler for mentions
        @self.app.message(
            ".*"
        )  # Catch all messages (filter by mention in the handler)
        def handle_message(message, say, client):
            """Handle incoming messages."""
            try:
                # Only process messages with bot mention or DM
                if not self._is_bot_mentioned(message):
                    return

                text = message.get("text", "").strip()
                user_id = message.get("user")
                channel = message.get("channel")
                thread_ts = message.get("thread_ts", message.get("ts"))

                # Show typing indicator
                self._show_typing(channel)

                # Process the message
                agent, query = self._parse_message(text)
                response = self._route_to_agent(agent, query, user_id)

                # Send response
                self._send_response(channel, response, thread_ts)

            except Exception as e:
                logger.error(f"Error handling message: {e}")
                say(f"❌ Erreur: {str(e)}", thread_ts=message.get("ts"))

        # App mention handler (for mentions in channels)
        @self.app.event("app_mention")
        def handle_mention(body, say, client):
            """Handle app mentions."""
            try:
                message = body["event"]
                text = message.get("text", "").strip()
                user_id = message.get("user")
                channel = message.get("channel")
                thread_ts = message.get("thread_ts", message.get("ts"))

                # Remove bot mention from text
                text = text.replace(f"<@{self.get_bot_id()}>", "").strip()

                # Show typing indicator
                self._show_typing(channel)

                # Process the message
                agent, query = self._parse_message(text)
                response = self._route_to_agent(agent, query, user_id)

                # Send response
                self._send_response(channel, response, thread_ts)

            except Exception as e:
                logger.error(f"Error handling mention: {e}")
                say(f"❌ Erreur: {str(e)}", thread_ts=body["event"].get("ts"))

    def _is_bot_mentioned(self, message: Dict[str, Any]) -> bool:
        """Check if bot is mentioned or it's a DM."""
        text = message.get("text", "")
        bot_id = self.get_bot_id()

        # Check for bot mention
        if f"<@{bot_id}>" in text:
            return True

        # Check for DM (no channel prefix)
        channel = message.get("channel", "")
        if channel.startswith("D"):  # Direct message
            return True

        return False

    def _parse_message(self, text: str) -> tuple[str, str]:
        """
        Parse message to extract agent name and query.
        Format: "Agent <NAME> <QUERY>" or just "<QUERY>"
        """
        text = text.strip()

        # Check for explicit agent mention
        agents = ["A", "B", "RVI", "SSS", "REM", "IRS", "FRP", "MIS"]
        for agent in agents:
            if text.lower().startswith(f"agent {agent.lower()}"):
                query = text[len(f"agent {agent}") :].strip()
                return agent.upper(), query
            if text.lower().startswith(agent.lower()):
                query = text[len(agent) :].strip()
                return agent.upper(), query

        # Default to Agent A
        return "A", text

    def _route_to_agent(
        self, agent_name: str, query: str, user_id: str
    ) -> Dict[str, Any]:
        """Route query to appropriate agent."""
        # This will be implemented in AgentInterface
        from .agent_interface import AgentInterface

        interface = AgentInterface()
        return interface.query_agent(agent_name, query, user_id)

    def _show_typing(self, channel: str):
        """Show typing indicator."""
        try:
            self.client.conversations_setTopic(channel=channel, topic="Typing...")
        except:
            pass  # Silently fail if we can't show typing

    def _send_response(self, channel: str, response: Dict[str, Any], thread_ts: str):
        """Send formatted response to Slack."""
        from .response_handler import ResponseHandler

        handler = ResponseHandler(self.client)
        handler.send_response(channel, response, thread_ts)

    def get_bot_id(self) -> str:
        """Get bot user ID."""
        try:
            auth_response = self.client.auth_test()
            return auth_response["user_id"]
        except Exception as e:
            logger.error(f"Error getting bot ID: {e}")
            return "U0000000000"

    def handle_request(self, request_body: str, signature: str, timestamp: str):
        """Handle incoming HTTP request from Slack."""
        return self.app.dispatch(
            body=request_body, signature=signature, timestamp=timestamp
        )
