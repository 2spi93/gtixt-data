#!/bin/bash

# Start Slack integration server
# Usage: ./start-slack-server.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Démarrage du serveur Slack Integration..."

# Check environment variables
if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "❌ SLACK_BOT_TOKEN non défini dans .env.local"
    echo "   Voir docs/SLACK_INTEGRATION_SETUP.md pour la configuration"
    exit 1
fi

if [ -z "$SLACK_SIGNING_SECRET" ]; then
    echo "❌ SLACK_SIGNING_SECRET non défini dans .env.local"
    echo "   Voir docs/SLACK_INTEGRATION_SETUP.md pour la configuration"
    exit 1
fi

# Load environment
if [ -f ".env.local" ]; then
    export $(cat .env.local | grep -v '^#' | xargs)
fi

# Install dependencies
echo "📦 Vérification des dépendances..."
pip install -q slack-bolt slack-sdk flask aiohttp 2>/dev/null || {
    echo "⚠️  Impossible d'installer les dépendances avec pip"
    echo "   Essayez: pip install slack-bolt slack-sdk flask aiohttp"
}

# Start server
PORT=${SLACK_INTERACTION_PORT:-5000}
echo "✅ Serveur Slack démarré sur port $PORT"
echo "   Webhook: http://localhost:$PORT/slack/events"
echo "   Santé: http://localhost:$PORT/slack/health"
echo ""
echo "Pour l'exposer publiquement, utilisez ngrok:"
echo "   ngrok http $PORT"
echo ""
echo "Mettez l'URL ngrok dans Slack Event Subscriptions"
echo ""

python slack_server.py
