# GTIXT Validation Framework - Deployment Guide

**Status**: 🚀 Ready for Testing  
**Last Updated**: 2025-01-31  
**Version**: v0.1 (Foundation)

---

## Overview

This document guides the deployment of the GTIXT institutional validation framework, which implements 6 IOSCO-aligned validation tests to ensure scoring integrity, stability, and auditability.

**Key Components**:
- ✅ Database schema (3 tables for events, metrics, alerts)
- ✅ Historical event data (20 ground-truth events)
- ✅ Prefect flow (6-hour validation suite)
- ✅ Frontend dashboard (`/validation` page)
- ✅ API endpoint (`/api/validation/metrics`)
- ✅ Slack alerting integration
- 🔧 (Pending) Real database integration

---

## Phase 1: Database Setup (15 minutes)

### 1.1 Prerequisites

```bash
# Verify database access
psql -U gpti -d gpti_data -c "SELECT version();"

# Verify Docker Compose (if running in containers)
docker-compose -f infra/docker-compose.yml ps
```

### 1.2 Deploy Migrations

```bash
# From /opt/gpti/gpti-data-bot/
cd /opt/gpti/gpti-data-bot

# Option A: Using provided script (recommended)
chmod +x deploy-validation.sh
./deploy-validation.sh local

# Option B: Manual deployment
psql -U gpti -d gpti_data -f src/gpti_data/db/migrations/002_create_validation_tables.sql
psql -U gpti -d gpti_data -f src/gpti_data/db/migrations/003_populate_historical_events.sql
```

### 1.3 Verify Tables Created

```bash
psql -U gpti -d gpti_data -c "
    SELECT table_name, 
           (SELECT COUNT(*) FROM information_schema.columns c 
            WHERE c.table_name = t.table_name) as column_count
    FROM information_schema.tables t
    WHERE table_schema = 'public' 
    AND table_name IN ('events', 'validation_metrics', 'validation_alerts')
    ORDER BY table_name;
"
```

**Expected Output**:
```
        table_name        | column_count
--------------------------+--------------
 events                   |           10
 validation_alerts        |            9
 validation_metrics       |           14
(3 rows)
```

### 1.4 Verify Historical Event Data

```bash
psql -U gpti -d gpti_data -c "
    SELECT event_type, COUNT(*) as count, 
           MAX(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as has_critical
    FROM events
    GROUP BY event_type
    ORDER BY count DESC;
"
```

**Expected Output**:
```
       event_type        | count | has_critical
------------------------+-------+--------------
 payout_controversy      |     4 |            1
 policy_change           |     6 |            0
 site_down               |     4 |            0
 regulatory_action       |     3 |            1
(4 rows)
```

---

## Phase 2: Python Dependencies (10 minutes)

### 2.1 Add Required Packages

```bash
# Update pyproject.toml with new dependencies
cat >> pyproject.toml << 'EOF'

# Validation framework dependencies
sqlalchemy = "^2.0.0"
psycopg2-binary = "^2.9.0"
requests = "^2.31.0"
EOF

# Install in development environment
pip install -e ".[dev]"
```

### 2.2 Verify Installation

```bash
python -c "from gpti_data.validation.db_utils import ValidationDB; print('✓ ValidationDB imported successfully')"
```

---

## Phase 3: Prefect Deployment (20 minutes)

### 3.1 Test Validation Flow Locally

```bash
# Test with mock snapshot ID
cd /opt/gpti/gpti-data-bot
python -m flows.validation_flow "universe_v0.1_2026-01-31"
```

**Expected Output**:
```
Computing coverage metrics for universe_v0.1_2026-01-31
Coverage: {'total_firms': 47, 'coverage_percent': 85.0, 'avg_na_rate': 12.0, 'agent_c_pass_rate': 92.0}
Computing stability metrics for universe_v0.1_2026-01-31
Stability: {'avg_score_change': 0.0234, 'top_10_turnover': 2, 'top_20_turnover': 4, 'verdict_churn_rate': 3.5}
Computing ground-truth validation for universe_v0.1_2026-01-31
Ground-truth: {'events_in_period': 3, 'events_predicted': 2, 'prediction_precision': 66.67}
...
Completed validation_flow for universe_v0.1_2026-01-31
```

### 3.2 Deploy to Prefect Server

```bash
# Authenticate with Prefect
prefect cloud login  # If using Prefect Cloud
# or
prefect config set PREFECT_API_URL="http://localhost:4200/api"  # Local server

# Deploy the validation_flow
prefect deployment create -f flows/validation_flow.py --name validation-6h

# Verify deployment
prefect deployment ls | grep validation
```

### 3.3 Schedule 6-Hourly Execution

```bash
# Set up schedule using Prefect CLI
prefect deployment set-schedule validation_flow/validation-6h --cron "0 */6 * * *"

# Or in deployment YAML (create prefect.yaml if not exists):
cat > prefect.yaml << 'EOF'
deployments:
  - name: validation-6h
    entrypoint: flows/validation_flow.py:validation_flow
    schedule:
      cron: "0 */6 * * *"  # Every 6 hours
    parameters:
      snapshot_id: "{{ env.LATEST_SNAPSHOT_ID }}"
EOF

prefect deploy --file prefect.yaml
```

---

## Phase 4: Slack Alerting (5 minutes)

### 4.1 Create Slack Webhook

1. Go to Slack workspace: https://gtixt.slack.com/apps
2. Search for "Incoming Webhooks"
3. Click "Add New Webhook to Workspace"
4. Select channel: `#validation-alerts` (create if needed)
5. Copy webhook URL: `https://hooks.slack.com/services/T.../B.../xxxx`

### 4.2 Configure Webhook in Environment

```bash
# Add to .env file
echo "SLACK_VALIDATION_WEBHOOK=https://hooks.slack.com/services/YOUR_WEBHOOK_URL" >> /opt/gpti/gpti-data-bot/.env

# Or set as environment variable
export SLACK_VALIDATION_WEBHOOK="https://hooks.slack.com/services/YOUR_WEBHOOK_URL"

# Verify
python -c "import os; print('Webhook configured' if os.environ.get('SLACK_VALIDATION_WEBHOOK') else 'Not configured')"
```

### 4.3 Test Alert Delivery

```bash
# Manually trigger validation flow with an artificially low coverage
python -c "
from gpti_data.validation.db_utils import ValidationDB
import os
os.environ['SLACK_VALIDATION_WEBHOOK'] = 'YOUR_WEBHOOK_URL'

# Create test alert
ValidationDB.create_alert(
    'COVERAGE_DROP', 'critical', 'coverage_percent',
    45.0, 70.0, 'Test alert: coverage dropped to 45%'
)
print('Test alert created')
"
```

---

## Phase 5: Frontend Integration (10 minutes)

### 5.1 Verify Validation Page

Navigate to: `http://localhost:3000/validation`

**Expected Content**:
- ✅ Alert display section (currently empty)
- ✅ Coverage metrics (47 firms, 85% coverage)
- ✅ Stability metrics (low turnover, 0.023 avg change)
- ✅ Ground-truth events (3 in period, 2 predicted)
- ✅ IOSCO framework explanation

### 5.2 API Endpoint

```bash
# Test metrics endpoint
curl http://localhost:3000/api/validation/metrics | jq .

# Expected response:
{
  "snapshot_id": "universe_v0.1_2026-01-31",
  "timestamp": "2026-01-31T14:30:00Z",
  "coverage": {
    "total_firms": 47,
    "coverage_percent": 85,
    "avg_na_rate": 12,
    "agent_c_pass_rate": 92
  },
  "stability": {
    "avg_score_change": 0.0234,
    "top_10_turnover": 2,
    "top_20_turnover": 4
  },
  "ground_truth": {
    "events_in_period": 3,
    "events_predicted": 2,
    "prediction_precision": 66.67
  },
  "alerts": []
}
```

### 5.3 Connect API to Database (Optional for v0.1)

Currently, the API returns mock data. To connect to real database:

```typescript
// pages/api/validation/metrics.ts
import { ValidationDB } from "@/gpti_data/validation/db_utils";

export default async (req, res) => {
  const latest = await ValidationDB.get_latest_snapshot();
  const metrics = await ValidationDB.get_validation_metrics(latest.id);
  res.json(metrics);
}
```

---

## Phase 6: Validation Testing (30 minutes)

### 6.1 Test Coverage Metrics (Test 1)

```bash
python -c "
from gpti_data.validation.db_utils import ValidationDB

metrics = ValidationDB.compute_coverage_metrics('universe_v0.1_2026-01-31')
print('Coverage Metrics:')
print(f'  Total Firms: {metrics[\"total_firms\"]}')
print(f'  Coverage: {metrics[\"coverage_percent\"]}%')
print(f'  NA Rate: {metrics[\"avg_na_rate\"]}%')
print(f'  Oversight Gate Pass Rate: {metrics[\"agent_c_pass_rate\"]}%')

# Alert if below thresholds
assert metrics['coverage_percent'] > 70, 'Coverage below 70%'
assert metrics['avg_na_rate'] < 25, 'NA rate above 25%'
assert metrics['agent_c_pass_rate'] > 80, 'Pass rate below 80%'
print('✓ All coverage checks passed')
"
```

### 6.2 Test Stability Metrics (Test 2)

```bash
python -c "
from gpti_data.validation.db_utils import ValidationDB

metrics = ValidationDB.compute_stability_metrics('universe_v0.1_2026-01-31')
print('Stability Metrics:')
print(f'  Avg Score Change: {metrics[\"avg_score_change\"]}')
print(f'  Top 10 Turnover: {metrics[\"top_10_turnover\"]}')
print(f'  Top 20 Turnover: {metrics[\"top_20_turnover\"]}')
print(f'  Verdict Churn Rate: {metrics[\"verdict_churn_rate\"]}%')

# Verify low volatility
assert metrics['avg_score_change'] < 0.1, 'Score volatility too high'
assert metrics['top_10_turnover'] <= 5, 'Top 10 turnover spiked'
print('✓ All stability checks passed')
"
```

### 6.3 Test Ground-Truth Validation (Test 4)

```bash
python -c "
from gpti_data.validation.db_utils import ValidationDB

metrics = ValidationDB.compute_ground_truth_validation('universe_v0.1_2026-01-31')
print('Ground-Truth Metrics:')
print(f'  Events in Period: {metrics[\"events_in_period\"]}')
print(f'  Events Predicted: {metrics[\"events_predicted\"]}')
print(f'  Prediction Precision: {metrics[\"prediction_precision\"]}%')

if metrics['events_in_period'] > 0:
    assert metrics['prediction_precision'] > 50, 'Prediction precision below 50%'
    print('✓ Ground-truth validation passed')
else:
    print('⏳ Insufficient historical data for full validation')
"
```

### 6.4 Test Alert Triggering

```bash
python -c "
from gpti_data.validation.db_utils import ValidationDB
from flows.validation_flow import check_alerts

# Test alert thresholds
alerts = check_alerts(
    coverage={'avg_na_rate': 30, 'coverage_percent': 60, 'agent_c_pass_rate': 75},
    stability={'top_10_turnover': 10},
    ground_truth={'events_in_period': 5, 'events_predicted': 2}
)

print(f'Generated {len(alerts)} alerts:')
for alert in alerts:
    print(f'  [{alert[\"severity\"]}] {alert[\"type\"]}: {alert[\"message\"]}')

assert len(alerts) >= 3, 'Expected at least 3 alerts'
print('✓ Alert triggering works correctly')
"
```

---

## Phase 7: Production Hardening (To Do)

### 7.1 Real Database Queries

Currently, `ValidationDB` uses mock SQL. To implement real queries:

```python
# src/gpti_data/validation/db_utils.py
# Replace mock queries with actual SQLAlchemy:

session.query(Snapshot).filter(
    Snapshot.snapshot_id == snapshot_id
).first()
```

**Estimated effort**: 2-3 hours

### 7.2 MinIO WORM Configuration

Enable Write-Once Read-Many on public snapshots:

```bash
# Configure MinIO object lock
mc retention set --governance 30d \
  minio/gpti-snapshots/universe_v0.1/latest.json

# Verify
mc retention info minio/gpti-snapshots/universe_v0.1/latest.json
```

### 7.3 Monthly Transparency Reports

Implement automated report generation:

```bash
# Create reports/ directory
mkdir -p /opt/gpti/gpti-data-bot/reports

# Add monthly generation task to validation_flow
```

**Estimated effort**: 2-3 hours

### 7.4 IOSCO Article 13 Response

Document in `/docs/IOSCO_Article_13_Response.md`:
- Methodology transparency ✅
- Evidence linkage ✅
- Ground-truth validation 🔧
- Governance structure ✅

**Estimated effort**: 1-2 hours

---

## Troubleshooting

### Database Connection Error

```bash
# Check PostgreSQL service
systemctl status postgresql
sudo systemctl start postgresql

# If Docker:
docker-compose -f infra/docker-compose.yml up -d postgres
```

### Migration Script Permission Denied

```bash
chmod +x deploy-validation.sh
./deploy-validation.sh
```

### Prefect Flow Fails

```bash
# Check logs
prefect flow-run view <RUN_ID>

# Debug locally
python -m flows.validation_flow "test-snapshot" --log-level=DEBUG
```

### Slack Webhook Not Working

```bash
# Verify webhook URL
curl -X POST $SLACK_VALIDATION_WEBHOOK \
  -H 'Content-type: application/json' \
  --data '{"text":"Test"}'

# Should return "ok" response
```

---

## Success Checklist

- [ ] Database tables created (3 tables, 20 events)
- [ ] Python dependencies installed
- [ ] Validation flow runs locally without errors
- [ ] Prefect deployment created and scheduled
- [ ] Slack webhook configured and tested
- [ ] `/validation` page accessible and shows metrics
- [ ] API endpoint `/api/validation/metrics` responds correctly
- [ ] All 6 validation tests execute successfully
- [ ] Alerts trigger on threshold violations
- [ ] Slack notifications received on alert

---

## Architecture Diagram

```
pipeline_flow (6h)
    ↓ exports snapshot
    ↓
validation_flow (6h) ← triggered automatically
    ├─ compute_coverage_metrics()
    ├─ compute_stability_metrics()
    └─ compute_ground_truth_validation()
        ↓
    check_alerts() ← detect anomalies
        ↓ if alerts
    send_alerts() → Slack webhook
        ↓
    store_metrics() → validation_metrics table
        ↓
dashboard fetch ← /api/validation/metrics
    ↓
/validation page (renders in browser)
```

---

## Next Steps

1. **This Week**: Deploy database + test validation_flow locally
2. **Next Week**: Implement real database queries + Prefect scheduling
3. **Week 3**: Connect frontend to database + automate reports
4. **Week 4**: IOSCO compliance documentation + partner integration

---

## Support

- **Technical Questions**: See [ROADMAP_v1.0_to_v1.1.md](ROADMAP_v1.0_to_v1.1.md)
- **Database Schema**: See [002_create_validation_tables.sql](src/gpti_data/db/migrations/002_create_validation_tables.sql)
- **API Reference**: See [pages/api/validation/metrics.ts](../gpti-site/pages/api/validation/metrics.ts)

