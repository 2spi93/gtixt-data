# GTIXT - Role Definitions and Responsibilities

**Version**: 1.0  
**Last Updated**: February 1, 2026  
**Purpose**: Clarify separation of concerns between bot, frontend, and test tools

---

## Executive Summary

The GTIXT project consists of three main components with **clearly defined roles**:

| Component | Purpose | Data Role | Environment |
|---|---|---|---|
| **gpti-data-bot** | Production data pipeline | Producer | Production |
| **gpti-site** | User interface | Consumer | All |
| **Test Generator** | Development tool | Synthetic data | Development only |

**Critical Principle**: **Bot produces, Frontend consumes, Test generator is temporary.**

---

## Component Roles

### 1. gpti-data-bot (Production Data Producer)

**Location**: `/opt/gpti/gpti-data-bot/`

#### Primary Responsibility
> **Produce authoritative, validated, production-ready firm data through automated crawling, extraction, scoring, and validation.**

#### Specific Roles

**Data Acquisition**:
- ✅ Crawl firm websites using Playwright/Puppeteer
- ✅ Store raw HTML evidence in MinIO
- ✅ Track crawl history and timestamps
- ❌ NEVER rely on user-submitted data
- ❌ NEVER accept data from frontend

**Data Extraction**:
- ✅ Parse HTML to extract structured data
- ✅ Identify rule sections, pricing, payout terms
- ✅ Detect changes vs previous crawls
- ✅ Store extracted data in PostgreSQL
- ❌ NEVER use frontend-generated data

**Scoring**:
- ✅ Apply methodology via 8 specialized agents:
  - **RVI**: Rule Volatility Index
  - **REM**: Regulatory Exposure Map
  - **FRP**: Future Risk Projection
  - **IRS**: Institutional Readiness Score
  - **IIP**: Integrity Index Project
  - **SSS**: Structural Sentiment Score
  - **SS**: Survivability Score
  - **MIS**: Model Integrity Score
- ✅ Calculate pillar scores (A-E)
- ✅ Generate total score (0-100)
- ❌ NEVER accept scores from frontend

**Validation**:
- ✅ Run Oversight Gate quality checks
- ✅ Calculate confidence (high/medium/low)
- ✅ Track NA rate (missing data %)
- ✅ Record validation events
- ✅ Reject low-quality data
- ❌ NEVER publish unvalidated data

**Publication**:
- ✅ Generate versioned snapshots (`universe_YYYY-MM-DD.json`)
- ✅ Calculate SHA256 hashes
- ✅ Publish to MinIO (`gpti-snapshots/`)
- ✅ Maintain immutable audit trail
- ❌ NEVER modify published snapshots

#### What Bot DOES NOT Do

- ❌ Serve HTTP endpoints directly to users
- ❌ Implement user interface
- ❌ Accept data from external sources
- ❌ Generate synthetic/test data
- ❌ Modify scores based on feedback

#### Key Outputs

**PostgreSQL Tables**:
- `firms`: Base firm records
- `crawl_history`: Timestamped crawl logs
- `rule_changes`: Detected modifications
- `scores`: Historical score data
- `validation_events`: Quality assurance records

**MinIO Buckets**:
- `gpti-raw/`: Raw HTML evidence
- `gpti-snapshots/`: Versioned JSON snapshots

**Snapshot Schema**: See [BOT_ARCHITECTURE.md](BOT_ARCHITECTURE.md#snapshot-schema)

---

### 2. gpti-site (Frontend / Data Consumer)

**Location**: `/opt/gpti/gpti-site/`

#### Primary Responsibility
> **Display bot-produced data to users through an intuitive, multilingual web interface with no data generation or scoring logic.**

#### Specific Roles

**Data Consumption**:
- ✅ Fetch snapshots from MinIO via API layer
- ✅ Parse JSON data for display
- ✅ Handle missing/incomplete data gracefully
- ✅ Cache data appropriately
- ❌ NEVER generate production scores
- ❌ NEVER implement scoring algorithms

**User Interface**:
- ✅ Rankings table with sorting/filtering
- ✅ Firm profile tearsheets
- ✅ Methodology explorer
- ✅ Data visualizations (charts, heatmaps)
- ✅ Multilingual support (EN/FR)
- ✅ Responsive design
- ❌ NEVER show unvalidated data

**API Layer**:
- ✅ `/api/firms`: List all firms
- ✅ `/api/firm`: Individual firm details
- ✅ Fetch from MinIO in production
- ✅ (Dev only) Fallback to test data
- ❌ NEVER compute scores in API

**Development Tools**:
- ✅ `scripts/generate-test-snapshot.js`: Generate synthetic test data
- ✅ Use test data when bot unavailable
- ❌ NEVER use test generator in production
- ❌ NEVER confuse test data with real data

#### What Frontend DOES NOT Do

- ❌ Crawl websites
- ❌ Parse HTML
- ❌ Implement scoring logic
- ❌ Validate data quality
- ❌ Generate production snapshots
- ❌ Write to MinIO or PostgreSQL
- ❌ Modify bot-produced data

#### Key Outputs

**Pages**:
- `/` - Homepage with hero
- `/rankings` - Full firm table
- `/firm/[id]` - Individual profiles
- `/methodology` - Framework docs
- `/data` - Data sources
- `/integrity` - Integrity beacon

**API Endpoints**:
- `/api/firms` - List firms
- `/api/firm?id=X` - Firm details

---

### 3. Test Data Generator (Development Tool)

**Location**: `/opt/gpti/gpti-site/scripts/generate-test-snapshot.js`

#### Primary Responsibility
> **Generate realistic synthetic data for frontend development when bot is not producing complete snapshots.**

#### Specific Roles

**Test Data Generation**:
- ✅ Fetch firm list from production MinIO (names/IDs only)
- ✅ Generate varied scores (15-95 range)
- ✅ Create realistic pillar scores
- ✅ Add detailed metrics (payout frequency, drawdown rules)
- ✅ Generate SHA256 hashes
- ✅ Calculate historical consistency
- ✅ Output to `/data/test-snapshot.json`
- ❌ NEVER used in production
- ❌ NEVER confused with real bot data

**Use Cases**:
- ✅ Frontend development without bot dependency
- ✅ UI/UX testing with realistic variation
- ✅ Demonstration/preview environments
- ✅ Regression testing for frontend
- ❌ Production deployment
- ❌ Real user-facing data

#### Lifecycle

**Current Status**: ACTIVE (bot not yet producing complete data)

**Migration Path**:
1. **Phase 1** (Current): Bot incomplete → Frontend uses test generator
2. **Phase 2** (Soon): Bot produces partial data → Frontend uses both
3. **Phase 3** (Production): Bot produces complete data → Test generator disabled

**Deprecation**:
- When: Bot produces snapshots with all required fields
- How: Remove or archive test generator script
- APIs: Remove local test data fallback logic

#### What Test Generator DOES NOT Do

- ❌ Crawl websites
- ❌ Extract real data
- ❌ Run in production
- ❌ Replace bot functionality
- ❌ Produce authoritative data

---

## Separation of Concerns

### Data Flow in Production

```
┌──────────────────────────────────────────────────────────────┐
│                   Production Data Flow                        │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Firm Websites (Source of Truth)                             │
│       │                                                       │
│       ▼                                                       │
│  gpti-data-bot (Crawler + Scorer + Validator)                │
│       │                                                       │
│       ▼                                                       │
│  MinIO Snapshots (Versioned, Immutable)                      │
│       │                                                       │
│       ▼                                                       │
│  gpti-site API (/api/firms, /api/firm)                       │
│       │                                                       │
│       ▼                                                       │
│  Frontend Pages (Rankings, Profiles)                         │
│       │                                                       │
│       ▼                                                       │
│  End Users (Traders, Institutions)                           │
│                                                               │
└──────────────────────────────────────────────────────────────┘

RULE: Data flows ONE WAY → No feedback from frontend to bot
```

### Data Flow in Development

```
┌──────────────────────────────────────────────────────────────┐
│                  Development Data Flow                        │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Production MinIO (Firm list only)                           │
│       │                                                       │
│       ▼                                                       │
│  Test Generator (Synthetic data creation)                    │
│       │                                                       │
│       ▼                                                       │
│  Local JSON File (/data/test-snapshot.json)                  │
│       │                                                       │
│       ▼                                                       │
│  gpti-site API (Checks local first)                          │
│       │                                                       │
│       ▼                                                       │
│  Frontend Pages (Development/Testing)                        │
│       │                                                       │
│       ▼                                                       │
│  Developers (UI/UX work)                                     │
│                                                               │
└──────────────────────────────────────────────────────────────┘

RULE: Test data NEVER reaches production environment
```

---

## Boundaries and Rules

### Bot Boundaries

**What Bot CAN Do**:
- ✅ Access public websites
- ✅ Parse HTML/PDF documents
- ✅ Store evidence in MinIO
- ✅ Write to PostgreSQL
- ✅ Calculate scores
- ✅ Validate data quality
- ✅ Publish snapshots

**What Bot CANNOT Do**:
- ❌ Serve HTTP to end users
- ❌ Render HTML pages
- ❌ Accept external data
- ❌ Modify published snapshots
- ❌ Skip validation

### Frontend Boundaries

**What Frontend CAN Do**:
- ✅ Read from MinIO
- ✅ Display data
- ✅ Filter/sort records
- ✅ Handle user interactions
- ✅ (Dev only) Use test data

**What Frontend CANNOT Do**:
- ❌ Crawl websites
- ❌ Score firms
- ❌ Validate data
- ❌ Write to MinIO/PostgreSQL
- ❌ Implement agent logic
- ❌ Use test data in production

### Test Generator Boundaries

**What Test Generator CAN Do**:
- ✅ Generate synthetic data
- ✅ Output to local file
- ✅ Fetch firm names from MinIO
- ✅ Create realistic variations

**What Test Generator CANNOT Do**:
- ❌ Run in production
- ❌ Replace bot functionality
- ❌ Write to MinIO
- ❌ Be used after bot is complete

---

## Agent Responsibilities

### Crawler Agent (Agent A)

**Role**: Fetch raw HTML from firm websites

**Inputs**: 
- Firm URLs from database
- Crawl schedule from Prefect

**Processing**:
- Use Playwright/Puppeteer for rendering
- Handle rate limiting
- Retry on failures
- Extract timestamps

**Outputs**:
- Raw HTML in MinIO (`gpti-raw/`)
- Crawl logs in PostgreSQL (`crawl_history`)

**DOES NOT**:
- Parse HTML (that's Extractor's job)
- Calculate scores (that's Scoring Agents' job)

---

### Extractor Agent (Agent B)

**Role**: Parse HTML and extract structured data

**Inputs**:
- Raw HTML from MinIO
- Extraction rules/patterns

**Processing**:
- Identify rule sections
- Extract pricing, payout terms
- Detect changes vs previous versions
- Normalize data formats

**Outputs**:
- Structured data in PostgreSQL (`firms`)
- Change logs in PostgreSQL (`rule_changes`)

**DOES NOT**:
- Crawl websites (that's Crawler's job)
- Calculate scores (that's Scoring Agents' job)

---

### RVI Agent (Rule Volatility Index)

**Role**: Calculate rule stability metric

**Spec**: [RVI_SPEC_v1.md](RVI_SPEC_v1.md)

**Inputs**: Rule change history from PostgreSQL

**Formula**: `RVI = (F × 0.30) + (A × 0.30) + (I × 0.25) + (C × 0.15)`

**Outputs**: 
- `metric_scores.rvi`: 0.0 (stable) to 1.0 (volatile)
- `rule_changes_frequency`: low/medium/high

**DOES NOT**:
- Crawl or extract data
- Score other aspects (only rule volatility)

---

### REM Agent (Regulatory Exposure Map)

**Role**: Assess jurisdictional risk

**Spec**: [REM_SPEC_v1.md](REM_SPEC_v1.md)

**Inputs**: Firm jurisdiction from PostgreSQL

**Processing**:
- Map jurisdiction to tier (A/B/C/D)
- Calculate regulatory risk
- Check model compatibility

**Outputs**:
- `jurisdiction_tier`: A (best) to D (worst)
- `metric_scores.rem`: Regulatory exposure score

**DOES NOT**:
- Determine jurisdiction (Extractor does that)
- Score other aspects

---

### FRP Agent (Future Risk Projection)

**Role**: Project future structural risk

**Spec**: [FRP_SPEC_v1.md](FRP_SPEC_v1.md)

**Inputs**: Historical scores, RVI, REM, MIS

**Processing**: Trend analysis and projection

**Outputs**:
- `metric_scores.frp_3m`, `frp_6m`, `frp_12m`
- `trajectory`: increasing/decreasing/stable

**DOES NOT**:
- Calculate current scores (uses others' outputs)
- Predict bankruptcy (only risk trajectory)

---

### IRS Agent (Institutional Readiness Score)

**Role**: Measure institutional maturity

**Spec**: [IRS_SPEC_v1.md](IRS_SPEC_v1.md)

**Inputs**: Governance, legal, operational, transparency, compliance data

**Formula**: `IRS = Σ(pillar_score × weight)`

**Outputs**:
- `metric_scores.irs`: Overall readiness
- `institutional_readiness.label`: Grade (Retail to Institution)

**DOES NOT**:
- Measure performance (only maturity)

---

### IIP Agent (Integrity Index Project)

**Role**: Cryptographic integrity verification

**Spec**: [IIP_SPEC_v1.md](IIP_SPEC_v1.md)

**Inputs**: Snapshot data

**Processing**: SHA256 hash generation

**Outputs**:
- `sha256`: 64-char hash
- `verification_hash`: Secondary hash
- `snapshot_history`: Historical hashes

**DOES NOT**:
- Score firms (only verifies data integrity)

---

### SSS Agent (Structural Sentiment Score)

**Role**: Aggregate sentiment from signals

**Spec**: [SSS_SPEC_v1.md](SSS_SPEC_v1.md)

**Inputs**: Rule clarity, payout consistency, change sentiment

**Outputs**: `metric_scores.sss`: Sentiment score

**DOES NOT**:
- Use user reviews (only structural signals)

---

### SS Agent (Survivability Score)

**Role**: Estimate firm longevity

**Spec**: [SS_SPEC_v1.md](SS_SPEC_v1.md)

**Inputs**: Firm age, stability, market presence

**Outputs**: `metric_scores.survivability`: Longevity probability

**DOES NOT**:
- Predict exact closure date (only probability)

---

### MIS Agent (Model Integrity Score)

**Role**: Assess business model quality

**Spec**: [MIS_SPEC_v1.md](MIS_SPEC_v1.md)

**Inputs**: Model type, fee structure, payout terms

**Outputs**: `metric_scores.mis`: Model quality score

**DOES NOT**:
- Score other aspects (only model integrity)

---

### Oversight Gate Agent (Agent C)

**Role**: Quality validation before publication

**Spec**: Validation Framework README

**Inputs**: Complete firm record with all scores

**Processing**:
- Check NA rate (<30% required)
- Verify confidence level
- Detect anomalies (score outliers)
- Validate required fields present

**Outputs**:
- `validation_status`: pass/fail/conditional
- `confidence`: high/medium/low
- Validation events in PostgreSQL

**DOES NOT**:
- Calculate scores (validates others' outputs)
- Modify data (only approves/rejects)

---

## Verification Checklist

Use this checklist to verify role separation is maintained:

### Bot Checklist

- [ ] Bot only crawls public websites (no private APIs)
- [ ] Bot stores all evidence in MinIO
- [ ] All scores calculated by agents (no manual overrides)
- [ ] Oversight Gate validates before publication
- [ ] Snapshots are versioned and immutable
- [ ] No HTTP endpoints served directly to users
- [ ] No dependency on frontend code

### Frontend Checklist

- [ ] Frontend only displays data (no scoring logic)
- [ ] APIs fetch from MinIO (production) or local test (dev)
- [ ] No crawling or HTML parsing
- [ ] No direct database writes
- [ ] Test generator clearly marked as dev-only
- [ ] No confusion between test and production data
- [ ] Graceful handling of missing data

### Test Generator Checklist

- [ ] Generator only runs in development
- [ ] Output file not committed to git (in .gitignore)
- [ ] Clearly documented as temporary tool
- [ ] Migration plan to bot data exists
- [ ] No production deployment
- [ ] Documentation warns against production use

---

## Common Violations to Avoid

### ❌ Frontend Implementing Scoring Logic

**Wrong**:
```javascript
// In frontend API endpoint
function calculateScore(firm) {
  return (firm.transparency * 0.3 + firm.payout * 0.3 + ...);
}
```

**Right**:
```javascript
// In frontend API endpoint
function getScore(firm) {
  return firm.score_0_100; // Use bot-calculated score
}
```

### ❌ Bot Serving HTTP Directly

**Wrong**:
```python
# In bot code
@app.route('/api/firms')
def get_firms():
    return jsonify(firms)
```

**Right**:
```python
# In bot code
def publish_snapshot(firms):
    minio_client.put_object('gpti-snapshots', 'latest.json', json.dumps(firms))
```

### ❌ Test Generator in Production

**Wrong**:
```bash
# In production deployment script
npm run build
node scripts/generate-test-snapshot.js  # ❌ NO!
npm start
```

**Right**:
```bash
# In production deployment script
npm run build
# APIs fetch from MinIO automatically
npm start
```

### ❌ Frontend Modifying Bot Data

**Wrong**:
```javascript
// In frontend
const adjustedScore = botScore * 1.1; // Boost by 10%
```

**Right**:
```javascript
// In frontend
const score = botScore; // Display as-is
```

---

## Enforcement

### Code Review Guidelines

1. **Bot PRs**: 
   - Verify no HTTP endpoints added
   - Check all scores validated by Oversight Gate
   - Ensure no frontend dependencies

2. **Frontend PRs**:
   - Verify no scoring algorithms
   - Check no crawling/parsing logic
   - Ensure test generator not in production path

3. **Documentation PRs**:
   - Keep role definitions updated
   - Reflect any architectural changes
   - Update diagrams if needed

### Testing Requirements

1. **Bot Tests**:
   - Unit tests for each agent
   - Integration tests for full pipeline
   - Validation tests for Oversight Gate

2. **Frontend Tests**:
   - E2E tests with test data
   - API tests with MinIO fallback
   - No tests that generate scores

3. **Separation Tests**:
   - Verify bot can run without frontend
   - Verify frontend can run with static snapshot
   - Test generator only runs in dev mode

---

## Migration Timeline

### Current State (v0.1)
- ✅ Bot: Infrastructure complete, agents in development
- ✅ Frontend: Complete UI with test data generator
- ⚠️ Data: Test generator active due to incomplete bot snapshots

### Target State (v1.0)
- ✅ Bot: All 9 agents producing complete scores
- ✅ Frontend: Consuming bot data exclusively
- ✅ Test Generator: Archived/disabled

### Migration Steps

1. **Bot Completion** (Est: Q2 2026)
   - [ ] Implement all 9 agents
   - [ ] Oversight Gate validation complete
   - [ ] Produce snapshots with all required fields

2. **Data Validation** (Est: Q2 2026)
   - [ ] Verify bot snapshots have all fields
   - [ ] Check NA rates <30%
   - [ ] Confirm confidence levels accurate

3. **Frontend Switch** (Est: Q3 2026)
   - [ ] Test APIs with bot data
   - [ ] Remove test generator from production
   - [ ] Archive test generator code

4. **Monitoring** (Est: Q3 2026)
   - [ ] Set up alerts for snapshot failures
   - [ ] Monitor API response times
   - [ ] Track data quality metrics

---

## Contact & Maintenance

**Documentation Owner**: GTIXT Development Team  
**Last Review**: February 1, 2026  
**Next Review**: Q2 2026  
**Related Docs**:
- [BOT_ARCHITECTURE.md](BOT_ARCHITECTURE.md)
- [TEST_DATA_GENERATOR.md](/opt/gpti/gpti-site/docs/TEST_DATA_GENERATOR.md)
- [Agent SPEC files](.)

---

**End of Role Definitions Document**
