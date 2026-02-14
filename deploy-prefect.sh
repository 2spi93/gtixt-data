#!/bin/bash
# Deploy GPTI pipeline to Prefect

cd /opt/gpti/gpti-data-bot

# Install Prefect if not already installed
pip install prefect

# Deploy the production flow
prefect deploy flows/production_flow.py:production_pipeline \
  --name "GTIXT Production Pipeline" \
  --description "Production pipeline: discover → crawl → export → score → verify → public export → validation → Slack" \
  --tag production \
  --interval 21600  # 6 hours in seconds

# Alternative: run manually for testing
# python flows/pipeline_flow.py