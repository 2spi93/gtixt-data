# GTIXT Data Bot - Architecture & Roles

**Version**: 1.0  
**Last Updated**: February 1, 2026

---

## Purpose

This document defines the **gpti-data-bot** architecture, component responsibilities, and separation of concerns with the **gpti-site** frontend.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      GTIXT ECOSYSTEM                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────┐         ┌────────────────────────┐  │
│  │   gpti-data-bot        │         │     gpti-site          │  │
│  │   (Backend/Pipeline)   │────────▶│   (Frontend/Web)       │  │
│  │                        │  Data   │                        │  │
│  │  - Crawling            │         │  - Display             │  │
│  │  - Scoring             │         │  - Rankings            │  │
│  │  - Validation          │         │  - Firm Profiles       │  │
│  │  - Snapshot Publishing │         │  - Data Visualization  │  │
│  └────────────────────────┘         └────────────────────────┘  │
│           │                                     │                │
│           │                                     │                │
│           ▼                                     ▼                │
│  ┌────────────────────────┐         ┌────────────────────────┐  │
│  │  MinIO Storage         │         │  PostgreSQL            │  │
│  │  (Production Snapshots)│         │  (Operational Data)    │  │
│  └────────────────────────┘         └────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Roles

### gpti-data-bot (Production Data Pipeline)

**Location**: `/opt/gpti/gpti-data-bot/`

#### Primary Responsibilities

1. **Web Crawling** (CRAWLER)
   - Fetch firm websites with Playwright/Puppeteer
   - Extract HTML, store raw evidence in MinIO
   - Timestamp and version all fetches
   - Handle rate limiting, retries, errors

2. **Data Extraction & Normalization** (shared)
   - Extraction logic lives in the crawler + domain agents
   - Identify rule sections, pricing, payout terms
   - Detect changes vs previous crawls
   - Store extracted data in PostgreSQL

3. **Scoring Engines** (Specialized Agents)
   - **RVI Agent**: Rule Volatility Index (frequency, amplitude, impact)
   - **REM Agent**: Regulatory Exposure Map (jurisdiction risk)
   - **FRP Agent**: Future Risk Projection (trajectory analysis)
   - **IRS Agent**: Institutional Readiness Score (maturity)
   - **IIP Agent**: Integrity Index Project (hash verification)
   - **SSS Agent**: Structural Sentiment Score (aggregated sentiment)
   - **MIS Agent**: Model Integrity Score (model quality)

4. **Validation Framework** (AGENT_C - Oversight Gate)
   - Quality checks before publication
   - Ground truth validation
   - Data completeness verification
   - Anomaly detection
   - Record validation events in PostgreSQL

5. **Snapshot Production**
   - Generate versioned snapshots: `universe_YYYY-MM-DD.json`
   - Calculate aggregated metrics
   - Add metadata (timestamp, version, hash)
   - Publish to MinIO `/gpti-snapshots/universe_v0.1_public/`

6. **Orchestration** (Prefect Flows)
   - Schedule daily/weekly/monthly runs
   - Pipeline coordination
   - Error handling and retries
   - Health monitoring

#### Data Outputs

**PostgreSQL Tables**:
- `firms`: Base firm records
- `crawl_history`: Timestamped crawl logs
- `rule_changes`: Detected rule modifications
- `scores`: Historical score data
- `validation_events`: Quality assurance records
- `validation_metrics`: Performance metrics
- `validation_alerts`: Issue notifications

**MinIO Buckets**:
- `gpti-raw/`: Raw HTML evidence
- `gpti-snapshots/`: Versioned JSON snapshots
- `gpti-validation/`: Validation artifacts

**Snapshot Schema** (Production):
```json
{
  "metadata": {
    "version": "v0.1",
    "timestamp": "2026-02-01T12:00:00Z",
    "record_count": 106,
    "hash": "36d717685b01..."
  },
  "records": [
    {
      "firm_id": "ftmocom",
      "name": "FTMO",
      "score_0_100": 87.5,
      "jurisdiction": "CY",
      "jurisdiction_tier": "C",
      "confidence": "high",
      "na_rate": 12,
      "pillar_scores": {
        "A_transparency": 0.89,
        "B_payout_reliability": 0.85,
        "C_risk_model": 0.87,
        "D_legal_compliance": 0.82,
        "E_reputation_support": 0.90
      },
      "metric_scores": {
        "rvi": 0.23,
        "rem": 0.45,
        "frp": 0.32
      },
      "detailed_metrics": {
        "payout_frequency": "monthly",
        "max_drawdown_rule": "10% daily, 5% overall",
        "rule_changes_frequency": "low"
      },
      "sha256": "a7b3c8d9e1f2...",
      "last_updated": "2026-01-30T08:00:00Z"
    }
  ]
}
```

---

### gpti-site (Frontend Application)

**Location**: `/opt/gpti/gpti-site/`

#### Primary Responsibilities

1. **Data Display**
   - Rankings table with sorting/filtering
   - Firm profile tearsheets
   - Methodology explorer
   - Data visualization (charts, heatmaps)

2. **API Layer**
   - `/api/firms`: List all firms with pagination
   - `/api/firm`: Individual firm details
   - Fetch from MinIO production snapshots
   - DB-backed endpoints use PostgreSQL when configured

3. **User Interface**
   - Multilingual support (EN/FR)
   - Responsive design
   - Accessibility features
   - Dark/light mode

4. **Development Tools** (NOT PRODUCTION)
   - Debug pages and test scripts for API verification

#### Data Consumption

**Production Mode**:
```javascript
// Fetch from MinIO
const response = await fetch(
  'http://51.210.246.61:9000/gpti-snapshots/universe_v0.1_public/_public/latest.json'
);
```

**Development Mode**:
```javascript
// Same as production: fetch from MinIO
const response = await fetch(
   'http://51.210.246.61:9000/gpti-snapshots/universe_v0.1_public/_public/latest.json'
);
```

---

## Separation of Concerns

| Concern | Bot Responsibility | Frontend Responsibility |
|---|---|---|
| **Data Acquisition** | ✅ Crawl websites | ❌ No crawling |
| **Data Extraction** | ✅ Parse HTML | ❌ No parsing |
| **Scoring** | ✅ Apply methodology | ❌ No scoring logic |
| **Validation** | ✅ Quality checks | ❌ No validation |
| **Storage** | ✅ PostgreSQL + MinIO | ❌ No persistence |
| **Display** | ❌ No UI | ✅ Render data |
| **API** | ❌ No endpoints | ✅ Serve to users |
| **Test Data** | ❌ Not used | ❌ Not used |

### Critical Rules

1. **Frontend NEVER generates production data**
   - Local test generators are archived
   - Production uses bot-generated snapshots

2. **Bot NEVER serves HTTP endpoints**
   - Bot produces files in MinIO
   - Frontend APIs read from MinIO

3. **Agents are backend-only**
   - RVI, REM, FRP, IRS, etc. run in bot pipeline
   - Frontend never implements agent logic

4. **Validation happens in bot**
   - Oversight Gate validates before publication
   - Frontend trusts published snapshots

---

## Agent Specifications

### CRAWLER
**Spec**: N/A (not yet documented)

**Role**: Web crawling and evidence collection

**Responsibilities**:
- Playwright/Puppeteer automation
- Rate limiting and retries
- Evidence storage in MinIO
- Crawl history tracking

**Outputs**: Raw HTML in `gpti-raw/` bucket

---

### Extraction & Normalization (Shared)
**Spec**: N/A (embedded)

**Role**: HTML parsing and structured data extraction embedded in crawler + agents

**Responsibilities**:
- Extract firm metadata (name, URL, model type)
- Parse rule sections (drawdown, payout, etc.)
- Detect rule changes vs previous versions
- Store extracted data in PostgreSQL

**Outputs**: Structured records in `firms` and `rule_changes` tables

---

### AGENT_C: Oversight Gate
**Spec**: Validation Framework README

**Role**: Quality assurance before publication

**Responsibilities**:
- Data completeness checks (NA rate)
- Ground truth validation
- Anomaly detection (score outliers)
- Publication approval/rejection
- Record validation events

**Outputs**: 
- Validation events in `validation_events` table
- Approved/rejected snapshots

**Key Metrics**:
- `na_rate`: Missing data percentage (should be <30%)
- `confidence`: high/medium/low based on data quality
- `validation_status`: pass/fail/conditional

---

### RVI Agent (Rule Volatility Index)
**Spec**: [RVI_SPEC_v1.md](RVI_SPEC_v1.md)

**Role**: Measure rule stability over time

**Formula**:
```
RVI = (F × 0.30) + (A × 0.30) + (I × 0.25) + (C × 0.15)

Where:
  F = Frequency Score (changes per year)
  A = Amplitude Score (magnitude of changes)
  I = Impact Score (trader impact severity)
  C = Consistency Score (cross-document coherence)
```

**Inputs**:
- Rule change history from PostgreSQL
- Previous snapshots for comparison
- Rule categories (risk, payout, fees, etc.)

**Outputs**:
- `metric_scores.rvi`: 0.0 (stable) to 1.0 (volatile)
- `rule_changes_frequency`: low/medium/high/stable/frequent

**Interpretation**:
- 0.00–0.20: Very stable rules
- 0.20–0.40: Minor changes
- 0.40–0.60: Moderate volatility
- 0.60–0.80: High volatility
- 0.80–1.00: Structural instability

---

### REM Agent (Regulatory Exposure Map)
**Spec**: [REM_SPEC_v1.md](REM_SPEC_v1.md)

**Role**: Assess jurisdictional and regulatory risk

**Inputs**:
- Firm jurisdiction (extracted by crawler/agents)
- Regulatory database (jurisdiction tiers)
- Model type compatibility matrix

**Outputs**:
- `jurisdiction`: ISO code (US, UK, CY, etc.)
- `jurisdiction_tier`: A (best), B, C, D (worst), UNKNOWN
- `metric_scores.rem`: Regulatory exposure risk (0-1)

**Jurisdiction Tiers**:
- **Tier A**: US, UK, AU, SG (regulated, transparent)
- **Tier B**: EU core (FR, DE, NL)
- **Tier C**: EU periphery (CY, MT)
- **Tier D**: Offshore (BZ, SC, VU)
- **UNKNOWN**: No clear jurisdiction

---

### FRP Agent (Future Risk Projection)
**Spec**: [FRP_SPEC_v1.md](FRP_SPEC_v1.md)

**Role**: Project future structural risk trajectory

**Formula**:
```
FRP = f(
  slope(score_history),
  RVI,
  REM,
  MIS_inverse,
   survivability_inverse (optional)
)
```

**Inputs**:
- Historical score trends
- RVI (instability)
- REM (regulatory risk)
- MIS (model quality)
- Survivability score

**Outputs**:
- `metric_scores.frp_3m`: 3-month projection
- `metric_scores.frp_6m`: 6-month projection
- `metric_scores.frp_12m`: 12-month projection
- `trajectory`: increasing/decreasing/stable

**Interpretation**:
- < 0.30: Stable outlook
- 0.30–0.50: Moderate risk
- 0.50–0.70: High risk
- > 0.70: Critical risk

---

### IRS Agent (Institutional Readiness Score)
**Spec**: [IRS_SPEC_v1.md](IRS_SPEC_v1.md)

**Role**: Measure institutional maturity

**Formula**:
```
IRS = Σ(pillar_score × weight)

Pillars:
  - Governance Maturity: 0.25
  - Legal Clarity: 0.20
  - Operational Discipline: 0.20
  - Data Transparency: 0.20
  - Compliance Compatibility: 0.15
```

**Inputs**:
- Rule clarity and versioning
- Legal documentation completeness
- Inverse RVI (stability)
- NA rate (data transparency)
- Jurisdiction tier (compliance)

**Outputs**:
- `metric_scores.irs`: Overall readiness (0-1)
- `institutional_readiness.label`: "Retail-grade" to "Institution-grade"

**Interpretation**:
- 0.00–0.30: Retail-grade
- 0.30–0.50: Semi-professional
- 0.50–0.70: Emerging institutional
- 0.70–0.85: Institutional-ready
- 0.85–1.00: Institution-grade

---

### IIP Agent (Integrity Index Project)
**Spec**: [IIP_SPEC_v1.md](IIP_SPEC_v1.md)

**Role**: Cryptographic snapshot integrity

**Responsibilities**:
- Generate SHA-256 hashes for snapshots
- Verify data integrity
- Detect tampering
- Provide audit trail

**Outputs**:
- `sha256`: 64-char hash of snapshot
- `verification_hash`: Secondary hash for cross-check
- `snapshot_history`: Array of previous hashes

**Usage**: Displayed on firm profiles as integrity beacon

---

### SSS Agent (Structural Sentiment Score)
**Spec**: [SSS_SPEC_v1.md](SSS_SPEC_v1.md)

**Role**: Aggregate sentiment from multiple signals

**Inputs**:
- Rule clarity
- Payout consistency
- Community feedback (if available)
- Change sentiment (positive/negative)

**Outputs**:
- `metric_scores.sss`: Sentiment score (0-1)
- Higher = more positive structural sentiment

---

### SS Agent (Survivability Score) (Deprecated)
**Spec**: [SS_SPEC_v1.md](SS_SPEC_v1.md)

**Role**: Historical concept, not active in the current 9-agent pipeline

---

### MIS Agent (Model Integrity Score)
**Spec**: [MIS_SPEC_v1.md](MIS_SPEC_v1.md)

**Role**: Assess business model quality

**Inputs**:
- Model type (CFD_FX, FUTURES, EQUITIES)
- Fee structure clarity
- Payout terms fairness
- Risk model soundness

**Outputs**:
- `metric_scores.mis`: Model quality (0-1)
- Higher = better model integrity

---

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                     Production Data Flow                          │
└──────────────────────────────────────────────────────────────────┘

  1. Web Sources (Firm Websites)
           │
           ▼
   2. CRAWLER
     - Fetches HTML
     - Stores in MinIO (gpti-raw/)
           │
           ▼
  3. Extraction & Normalization (shared)
     - Parses HTML
     - Extracts structured data
     - Stores in PostgreSQL (firms, rule_changes)
           │
           ▼
   4. Scoring Agents (RVI, REM, FRP, IRS, IIP, SSS, MIS)
     - Calculate metrics
     - Store in PostgreSQL (scores)
           │
           ▼
   5. AGENT_C (Oversight Gate)
     - Validates data quality
     - Checks NA rate, confidence
     - Records validation events
           │
           ▼
  6. Snapshot Producer
     - Aggregates PostgreSQL data
     - Generates JSON snapshot
     - Calculates metadata (hash, timestamp)
     - Publishes to MinIO (gpti-snapshots/)
           │
           ▼
  7. Frontend API (/api/firms, /api/firm)
     - Fetches from MinIO
     - Serves to users
           │
           ▼
  8. Frontend Pages (Rankings, Firm Profiles)
     - Displays data
     - User interaction
```

---

## Current Status (v0.1)

### ✅ Completed

- PostgreSQL schema with 3 core tables
- Validation framework with event logging
- Prefect flow orchestration
- MinIO storage buckets
- Agent specifications (SPEC files)
- Snapshot schema definition

### 🔧 In Progress

- Agent A (Crawler) implementation
- Agent B (Extractor) implementation
- Agent C (Oversight Gate) logic
- Scoring agent implementations
- Production snapshot generation

### ❌ Known Issues

**Production Snapshot Incomplete**:
- Current MinIO snapshot (`36d717685b01.json`) has placeholder data
- All firms show score = 42.0 (not real scores)
- Missing fields: `jurisdiction_tier`, `confidence`, `na_rate`
- **Workaround removed**: Frontend no longer uses a local test generator; APIs surface MinIO data as-is

---

## Migration Path: Test Data → Production Data

### Phase 1: Development (Current)
- APIs use MinIO snapshots directly
- No local test snapshot fallback
- UI/UX validation relies on real pipeline output

### Phase 2: Bot Alpha Testing
- Bot starts producing partial snapshots
- Frontend uses MinIO data only
- Gradual validation of bot output

### Phase 3: Production Deployment
- Bot produces complete snapshots daily
- APIs use MinIO exclusively
- Local test data archived

### Checklist for Phase 3

- [ ] All 9 agents fully implemented
- [ ] Bot produces snapshots with all required fields
- [ ] Snapshot validation passes (NA rate <30%, confidence ≥ medium)
- [ ] Historical data includes 12+ months
- [ ] SHA-256 hashes generated correctly
- [ ] Frontend API tests pass with production data
- [ ] Performance benchmarks met (API response <2s)
- [ ] Documentation updated
- [ ] Monitoring/alerting configured
- [ ] Backup/disaster recovery plan

---

## Development Guidelines

### For Bot Developers

1. **Never modify frontend code**
   - Bot produces data files only
   - No HTTP endpoints in bot

2. **Validate before publishing**
   - Run Oversight Gate on all snapshots
   - Never publish incomplete data

3. **Version all snapshots**
   - Use `universe_YYYY-MM-DD.json` format
   - Keep historical versions for auditing

4. **Document agent changes**
   - Update SPEC files when methodology changes
   - Increment version numbers

### For Frontend Developers

1. **Never implement scoring logic**
   - Scoring belongs in bot agents
   - Frontend displays data only

2. **Use MinIO snapshots in all environments**
   - No local test snapshot fallback
   - Validate against production schema

3. **Gracefully handle missing data**
   - Show "—" for unavailable fields
   - Never crash on incomplete snapshots

4. **Test with live data sources**
   - MinIO snapshots
   - PostgreSQL-backed endpoints

---

## Troubleshooting

### Issue: Frontend shows all firms with score 42

**Diagnosis**: Using incomplete production snapshot

**Solution**: 
```bash
# Verify MinIO snapshot availability
curl -I "http://51.210.246.61:9000/gpti-snapshots/universe_v0.1_public/_public/latest.json"
```

### Issue: Bot not producing snapshots

**Diagnosis**: Pipeline not running or failing

**Solution**:
```bash
# Check Prefect flows
cd /opt/gpti/gpti-data-bot
prefect deployment ls

# Check logs
tail -f logs/bot.log

# Run validation
python flows/validation_flow.py
```

### Issue: Snapshot missing required fields

**Diagnosis**: Agent not populating fields correctly

**Solution**:
1. Check agent SPEC for field requirements
2. Verify PostgreSQL schema includes field
3. Test agent in isolation
4. Check Oversight Gate validation rules

---

## Contact & Maintenance

**Project**: GTIXT Data Bot & Frontend  
**Documentation**: `/opt/gpti/gpti-data-bot/docs/`  
**Issue Tracking**: (To be configured)  
**Last Audit**: February 1, 2026  
**Next Review**: Q2 2026  

---

**End of Architecture Document**
