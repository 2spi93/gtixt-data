#!/bin/bash
set -e

cd /opt/gpti/gpti-data-bot/infra

echo "🚀 Deploying Ollama healthcheck schedule (every 10 minutes)"

sudo docker compose exec -T bot prefect deployment create -f /app/flows/healthcheck_ollama_flow.py --name healthcheck-10m
sudo docker compose exec -T bot prefect deployment set-schedule healthcheck_ollama_flow/healthcheck-10m --cron "*/10 * * * *"

echo "✅ Healthcheck deployment scheduled (*/10 * * * *)"
