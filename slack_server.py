"""Flask server for Slack event handling."""

import os
import logging
from flask import Flask, request, jsonify
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

# Import our Slack integration
from src.slack_integration.events import SlackEventHandler

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize Flask app
app = Flask(__name__)

# Initialize Slack handler
slack_handler = SlackEventHandler()
slack_request_handler = SlackRequestHandler(slack_handler.app)


@app.route("/slack/events", methods=["POST"])
def slack_events():
    """Handle Slack events webhook."""
    return slack_request_handler.handle(request)


@app.route("/slack/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify(
        {
            "status": "healthy",
            "slack_bot_token": "configured"
            if os.getenv("SLACK_BOT_TOKEN")
            else "missing",
            "slack_signing_secret": "configured"
            if os.getenv("SLACK_SIGNING_SECRET")
            else "missing",
        }
    )


@app.route("/slack/info", methods=["GET"])
def info():
    """Get bot information."""
    try:
        bot_id = slack_handler.get_bot_id()
        return jsonify(
            {
                "bot_id": bot_id,
                "agents": list(slack_handler._route_to_agent.__self__.AGENT_DESCRIPTIONS.keys()),
                "webhook_url": os.getenv("SLACK_WEBHOOK_URL", "").split("/")[-1] if os.getenv("SLACK_WEBHOOK_URL") else "not configured",
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.errorhandler(500)
def handle_error(error):
    """Handle errors."""
    logger.error(f"Server error: {error}")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app_token = os.getenv("SLACK_APP_TOKEN")
    if app_token:
        logger.info("Starting Slack bot in Socket Mode")
        SocketModeHandler(slack_handler.app, app_token).start()
    else:
        port = int(os.getenv("SLACK_INTERACTION_PORT", 5000))
        logger.info("Starting Slack bot in Events API mode")
        app.run(host="0.0.0.0", port=port, debug=False)
