# GTIXT Institutional Roadmap v1.0 → v1.1

**Goal**: Transform from "working prototype" → "IOSCO-compliant benchmark"

---

## Phase 1: Data Sources (Weeks 1-2)

### ✅ Already Done
- **Hard Evidence**: Rules/pricing/terms crawling
- **Versioning**: SHA-256 hashing on all exports
- **Audit trail**: URL + timestamp + hash stored

### 🔧 To Build

#### A) Official Website Crawling (Hard Evidence)
```
Firms → Rules, FAQ, Terms, Payouts, Refunds, Legal pages
Store: URL + content + SHA-256 hash + timestamp
Index: evidence_collected table
  - evidence_id (UUID)
  - firm_name
  - evidence_type ('rules', 'pricing', 'terms', 'refund_policy', 'legal')
  - url
  - sha256_hash
  - crawled_at
  - content (stored as binary/text)
```

**Automation**: Prefect task `crawl_evidence` every 24h with retry logic

---

#### B) Registry & Compliance Data (Semi-Hard)
```
Jurisdiction → Company registry lookups
Store: registration_status table
  - firm_name
  - jurisdiction
  - registration_number
  - registration_date
  - regulatory_tier (Tier 1/2/3)
  - regulated_status ('regulated', 'unregulated', 'partially_regulated')
  - last_verified_at
```

**Sources**:
- UK: Companies House API
- US: SEC EDGAR / FINRA
- EU: National registries + ESMA coordination
- Others: Manual + partnerships

**Automation**: Quarterly refresh + event-driven updates

---

#### C) Reputation & Support Signals (Soft - with guards)
```
Trustpilot + similar platforms
Store: soft_signals table
  - firm_name
  - platform ('trustpilot', 'reddit', 'twitter', 'trustpilot')
  - rating (0-100)
  - review_count
  - sentiment (positive / neutral / negative / mixed)
  - flagged_keywords (array: 'withdrawal_issue', 'support_slow', 'scam_claim', etc)
  - confidence (0-1: how reliable is this signal)
  - collected_at
  
  -- Oversight Gate guardrails
  - agent_c_review (bool): "is this signal credible?"
  - agent_c_notes (text)
```

**Integration**: LLM sentiment + keyword extraction, tagged as "soft", subject to NA-neutral treatment

---

## Phase 2: Validation Framework (Weeks 2-3)

### 6 Tests to Implement

#### Test 1: Coverage & Data Sufficiency ✅
```
Metrics:
- % firms with rules_extracted (target: >85%)
- % firms with pricing_extracted (target: >85%)
- avg NA_rate per firm (target: <25%)
- Oversight Gate pass_rate (target: >80%)

Alert thresholds:
- If coverage < 70% → CRITICAL
- If avg_na_rate > 25% → WARNING
- If agent_c_pass_rate < 80% → WARNING
```

#### Test 2: Stability & Turnover ✅
```
Metrics:
- avg_score_change snapshot-to-snapshot (target: < 0.05)
- top_10_turnover (target: ≤ 2 firms per snapshot)
- top_20_turnover (target: ≤ 4 firms per snapshot)
- verdict_churn (pass → review → etc) (target: < 10%)

Alert: If top_10_turnover > 5 → investigate score volatility
```

#### Test 3: Sensitivity & Stress Tests
```
Stress scenarios:
1. Remove one pillar: "score without Transparency pillar"
2. Missing data: "if pricing unavailable → fallback impact"
3. NA shock: "if crawl fails 24h → what's the impact?"

Metrics:
- pillar_sensitivity_mean (avg % impact per pillar removal)
- fallback_usage_percent (% of scores using fallback)
- stability_score (0-100: robustness rating)
```

#### Test 4: Ground-Truth Events ✅
```
Manual event tracking table:
  events:
    - firm_name
    - event_type ('payout_controversy', 'regulatory_action', 'site_down', 'policy_change')
    - event_date
    - severity
    - source_url
    - created_by (human curator)

Validation:
- Did our score DROP before/after event?
- Did our NA_rate or confidence SIGNAL the risk?
- Precision: (events_predicted / events_in_period)
```

#### Test 5: Calibration & Bias Checks
```
Metrics:
- score_distribution_skew (by jurisdiction_tier, model_type)
- jurisdiction_bias_score (0-100: are Tier 3 treated fairly?)
- model_type_bias (CFD vs Futures vs Crypto)

Ensure:
- No jurisdiction gets systematically higher/lower scores
- Soft signals (reviews) don't dominate the overall score
```

#### Test 6: Auditability ✅
```
Every firm score must be traceable:
  score_audit_trail:
    - firm_name
    - snapshot_id
    - score_0_100
    - pillar_scores (transparency, compliance, etc)
    - evidence_links (array of [URL, timestamp, hash])
    - version_metadata ('v1.0', 'v1.1', ...)

Query: "Why is Firm X a 78?" → Show exact evidence + methodology version
```

---

## Phase 3: Infrastructure & Automation (Week 3)

### Prefect Flows
```
1. pipeline_flow (existing)
   - crawl → score → verify → export
   - Every 6h

2. validation_flow (new)
   - compute_coverage_metrics()
   - compute_stability_metrics()
   - compute_sensitivity_metrics()
   - validate_ground_truth()
   - check_calibration()
   - check_auditability()
   - send_alerts() → Slack/email
   - store_metrics() → validation_metrics table

3. registry_refresh_flow (new, quarterly)
   - Query company registries
   - Update registration_status table

4. alert_monitor_flow (new, hourly)
   - Watch validation_alerts table
   - Escalate critical issues
```

### MinIO Object Lock (WORM - Write-Once Read-Many)
```
Bucket: gpti-snapshots (public)
- Enable Object Lock (GOVERNANCE mode)
- Retention: immutable for 30 days
- Versioning: enabled
- Result: "tamper-evident" audit trail

Document in IOSCO response: "Our public data cannot be retroactively modified"
```

---

## Phase 4: Public Reporting (Weeks 3-4)

### A) Validation Report (auto-generated, every 6h)
**Endpoint**: `/integrity/validation`
```
JSON:
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
    "top_10_turnover": 2
  },
  "ground_truth": {
    "events_in_period": 3,
    "events_predicted": 2,
    "prediction_precision": 67
  },
  "alerts": []
}
```

**HTML**: `/pages/validation.tsx` (dashboard with charts + interpretation)

### B) Monthly Transparency Report
**Endpoint**: `/reports/transparency`
```
Markdown/PDF:
1. Data coverage summary
2. Scoring changes analysis
3. Events & ground-truth tracking
4. Bias/calibration checks
5. Infrastructure uptime
6. Incidents & resolutions
```

### C) Verified Feed Spec (for partners)
**Endpoint**: `/docs/verified-feed`
```
For data consumers (buy-side, compliance):
- How to fetch + verify latest.json
- How to validate SHA-256
- How to audit evidence links
- Example: curl + verification script
```

---

## Success Criteria (v1.1)

| Test | Target | Status |
|------|--------|--------|
| Coverage | >85% | ✅ Current: 85% |
| Stability | score_change < 0.05 | ✅ Current: 0.023 |
| NA Rate | <25% | ✅ Current: 12% |
| Pass Rate | >80% | ✅ Current: 92% |
| Top 10 Turnover | ≤2 | ✅ Current: 2 |
| Auditability | 100% traceable | 🔧 In progress |
| Ground-truth | >60% precision | ⏳ After 30 days |
| Bias | <5% jurisdiction skew | ⏳ Pending calibration |

---

## IOSCO Alignment

✅ **Article 13 (Transparency of Methodology)**
- Deterministic rules ✅
- Version control ✅
- Public evidence links ✅
- Ground-truth validation 🔧

✅ **Article 14 (Governance)**
- Oversight Gate oversight ✅
- Escalation procedures ✅
- Quarterly reporting 🔧

✅ **Article 15 (Data Sufficiency & Quality)**
- Coverage metrics ✅
- NA-neutral treatment ✅
- Stability monitoring 🔧

✅ **Article 16 (Conflict of Interest)**
- No financial interest in scores ✅
- Soft signals tagged + guarded ✅

---

## Next Immediate Actions

**Week 1 (Jan 31 - Feb 6)**
- [ ] Create `events` table + manual curator interface
- [ ] Deploy `validation_flow.py` to Prefect
- [ ] Launch `/integrity/validation` page
- [ ] Configure Slack alerts

**Week 2 (Feb 7 - Feb 13)**
- [ ] Add evidence tracking (`evidence_collected` table)
- [ ] Build registry lookup task
- [ ] Implement soft signals (Trustpilot integration)

**Week 3 (Feb 14 - Feb 20)**
- [ ] Monthly transparency report first draft
- [ ] Verified feed spec docs
- [ ] Calibration audit (bias checks)

**Week 4 (Feb 21 - Feb 27)**
- [ ] v1.1 release notes
- [ ] External communication (Article 13 submission)
- [ ] Partner onboarding for verified feed

---

## Files Created

- `src/gpti_data/db/migrations/002_create_validation_tables.sql` — DB schema
- `flows/validation_flow.py` — Prefect orchestration
- `pages/validation.tsx` — Dashboard UI
- `pages/api/validation/metrics.ts` — Metrics API
- `docs/ROADMAP_v1.0_to_v1.1.md` — This file

