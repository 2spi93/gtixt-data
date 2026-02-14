# GTIXT Validation Framework - Documentation Index

**Last Updated**: 2025-01-31  
**Status**: ✅ Foundation Complete  
**Quick Links**: [QuickStart](#quickstart) • [Deployment](#deployment) • [Architecture](#architecture)

---

## Core Documents

### 📚 START HERE

**[QUICKSTART.md](QUICKSTART.md)** — 5-minute quick start guide
- Deploy database in 1 command
- Test validation flow locally
- View dashboard
- Verify API

**[VALIDATION_FRAMEWORK_README.md](VALIDATION_FRAMEWORK_README.md)** — Framework overview
- What is the validation framework?
- 6 validation tests explained
- Architecture diagram
- Implementation status
- Key files location

---

### 📋 DEPLOYMENT GUIDES

**[DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md)** — Step-by-step deployment (7 phases)
- Phase 1: Database setup (15 min)
- Phase 2: Python dependencies (10 min)
- Phase 3: Prefect deployment (20 min)
- Phase 4: Slack alerting (5 min)
- Phase 5: Frontend integration (10 min)
- Phase 6: Validation testing (30 min)
- Phase 7: Production hardening
- Troubleshooting guide

**[QUICKSTART.md](QUICKSTART.md)** — Fast setup (5 minutes)
- Minimal steps
- Key commands
- Success checklist
- Troubleshooting

---

### 🏗️ ARCHITECTURE & DESIGN

**[ROADMAP_v1.0_to_v1.1.md](ROADMAP_v1.0_to_v1.1.md)** — Complete architecture (280 lines)
- 3-phase transition plan
- Data sources architecture
- 6 validation tests detailed
- IOSCO alignment mapping
- Success criteria
- File checklist

**[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** — What was built (complete overview)
- Database infrastructure
- Python interface
- Refactored Prefect flow
- Frontend dashboard
- API endpoint
- Known limitations
- IOSCO alignment progress
- Architecture decisions & rationale

---

### 📊 PROJECT MANAGEMENT

**[PROJECT_STATUS.md](PROJECT_STATUS.md)** — Current status & timeline (4-week roadmap)
- Executive summary
- Completed deliverables
- Work in progress
- Validation tests status
- Code quality metrics
- Risk assessment
- Budget & timeline
- Success criteria checklist

---

## Documentation Structure

```
docs/
├── QUICKSTART.md                      ← START HERE (5 min)
├── VALIDATION_FRAMEWORK_README.md     ← Framework overview
├── DEPLOYMENT_VALIDATION.md           ← Step-by-step guide
├── ROADMAP_v1.0_to_v1.1.md           ← Architecture & design
├── IMPLEMENTATION_SUMMARY.md          ← What was built
├── PROJECT_STATUS.md                  ← Timeline & status
└── INDEX.md                           ← This file

src/gpti_data/db/migrations/
├── 002_create_validation_tables.sql   ← Database schema
└── 003_populate_historical_events.sql ← Historical data

src/gpti_data/validation/
└── db_utils.py                        ← Database interface

flows/
└── validation_flow.py                 ← Prefect orchestration

pages/
├── validation.tsx                     ← Dashboard
└── api/validation/
    └── metrics.ts                     ← API endpoint
```

---

## Quick Navigation

### By Role

**🔧 DevOps / Deployment Engineers**
1. Start: [QUICKSTART.md](QUICKSTART.md)
2. Deploy: [DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md)
3. Monitor: [PROJECT_STATUS.md](PROJECT_STATUS.md)

**👨‍💻 Backend Engineers**
1. Architecture: [ROADMAP_v1.0_to_v1.1.md](ROADMAP_v1.0_to_v1.1.md)
2. Implementation: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
3. Code: `src/gpti_data/validation/db_utils.py`

**🎨 Frontend Engineers**
1. Framework: [VALIDATION_FRAMEWORK_README.md](VALIDATION_FRAMEWORK_README.md)
2. Dashboard: `pages/validation.tsx`
3. API: `pages/api/validation/metrics.ts`

**📊 Product Managers**
1. Overview: [VALIDATION_FRAMEWORK_README.md](VALIDATION_FRAMEWORK_README.md)
2. Timeline: [PROJECT_STATUS.md](PROJECT_STATUS.md)
3. Roadmap: [ROADMAP_v1.0_to_v1.1.md](ROADMAP_v1.0_to_v1.1.md)

**🏢 Executives**
1. Status: [PROJECT_STATUS.md](PROJECT_STATUS.md) (Executive Summary)
2. Roadmap: [ROADMAP_v1.0_to_v1.1.md](ROADMAP_v1.0_to_v1.1.md) (IOSCO Alignment)
3. Framework: [VALIDATION_FRAMEWORK_README.md](VALIDATION_FRAMEWORK_README.md)

---

## By Task

### "I need to deploy this today"
→ [QUICKSTART.md](QUICKSTART.md) + [DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md)

### "I need to understand the architecture"
→ [ROADMAP_v1.0_to_v1.1.md](ROADMAP_v1.0_to_v1.1.md)

### "What was actually built?"
→ [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

### "What's the timeline?"
→ [PROJECT_STATUS.md](PROJECT_STATUS.md)

### "How do I fix errors?"
→ [DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md#troubleshooting)

### "What are the 6 tests?"
→ [VALIDATION_FRAMEWORK_README.md](VALIDATION_FRAMEWORK_README.md#the-6-validation-tests)

### "How is this IOSCO compliant?"
→ [ROADMAP_v1.0_to_v1.1.md](ROADMAP_v1.0_to_v1.1.md#iosco-alignment)

### "What needs to be done next?"
→ [PROJECT_STATUS.md](PROJECT_STATUS.md#work-in-progress-next-4-weeks)

---

## File Guide

### Database

| File | Purpose | Size | Audience |
|------|---------|------|----------|
| `002_create_validation_tables.sql` | Table definitions | 195 lines | DBAs, Backend engineers |
| `003_populate_historical_events.sql` | 20 historical events | 80 lines | DBAs, Validation experts |

### Python

| File | Purpose | Size | Audience |
|------|---------|------|----------|
| `db_utils.py` | Database interface | 360 lines | Backend engineers |
| `validation_flow.py` | Prefect orchestration | 150 lines | Backend engineers, DevOps |

### Frontend

| File | Purpose | Size | Audience |
|------|---------|------|----------|
| `pages/validation.tsx` | Dashboard page | 430 lines | Frontend engineers |
| `pages/api/validation/metrics.ts` | REST API | 50 lines | Frontend/Backend engineers |

### Documentation

| File | Purpose | Size | Audience |
|------|---------|------|----------|
| QUICKSTART.md | Fast setup | 150 lines | Everyone |
| VALIDATION_FRAMEWORK_README.md | Framework overview | 300 lines | Everyone |
| DEPLOYMENT_VALIDATION.md | Step-by-step guide | 400 lines | DevOps, Engineers |
| ROADMAP_v1.0_to_v1.1.md | Architecture | 280 lines | Engineers, PMs |
| IMPLEMENTATION_SUMMARY.md | What was built | 400 lines | Engineers, Stakeholders |
| PROJECT_STATUS.md | Timeline & status | 350 lines | Managers, Stakeholders |
| INDEX.md | Documentation index | - | Everyone |

---

## Key Concepts

### The 6 Validation Tests

1. **Coverage** — Are all firms sufficiently documented?
2. **Stability** — Do scores change too much between snapshots?
3. **Sensitivity** — Are scores robust to missing data?
4. **Ground-Truth** — Do scores predict real-world events?
5. **Calibration** — Is there systematic bias by jurisdiction?
6. **Auditability** — Is every score fully traceable?

See [VALIDATION_FRAMEWORK_README.md](VALIDATION_FRAMEWORK_README.md#the-6-validation-tests) for details.

### The 3 Database Tables

1. **events** — External ground-truth events (20 historical)
2. **validation_metrics** — Test results per snapshot
3. **validation_alerts** — Triggered anomalies

See [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md#database-infrastructure) for schema.

### The 4-Week Timeline

| Week | Phase | Status |
|------|-------|--------|
| Week 1 | Foundation (v0.1) | ✅ Complete |
| Week 2 | Prefect + Database integration | 🔧 In Progress |
| Week 3 | Tests 3&5 + Production hardening | ⏳ Pending |
| Week 4 | IOSCO compliance + Release | ⏳ Pending |

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for details.

---

## Common Questions

**Q: Where do I start?**
A: [QUICKSTART.md](QUICKSTART.md) — 5 minutes to get running locally.

**Q: How do I deploy to production?**
A: [DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md) — 7 phases with step-by-step instructions.

**Q: What's the architecture?**
A: [ROADMAP_v1.0_to_v1.1.md](ROADMAP_v1.0_to_v1.1.md) — Complete system design.

**Q: What was actually built?**
A: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) — Detailed overview of all components.

**Q: What's next?**
A: [PROJECT_STATUS.md](PROJECT_STATUS.md#work-in-progress-next-4-weeks) — 4-week roadmap.

**Q: Is this IOSCO compliant?**
A: [ROADMAP_v1.0_to_v1.1.md](ROADMAP_v1.0_to_v1.1.md#iosco-alignment) — Articles 13-16 mapped.

**Q: How do I fix errors?**
A: [DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md#troubleshooting) — Common issues & solutions.

---

## Commands Quick Reference

```bash
# Deploy database
./deploy-validation.sh

# Test validation flow
python -m flows.validation_flow "universe_v0.1_2026-01-31"

# View dashboard
open http://localhost:3000/validation

# Test API
curl http://localhost:3000/api/validation/metrics | jq .

# Deploy to Prefect
prefect deployment create -f flows/validation_flow.py

# Schedule 6-hourly
prefect deployment set-schedule validation_flow/validation-6h --cron "0 */6 * * *"
```

---

## Document Versions

| Document | v0.1 | v0.2 | v1.0 |
|----------|------|------|------|
| QUICKSTART.md | ✅ | ↻ | ↻ |
| VALIDATION_FRAMEWORK_README.md | ✅ | ↻ | ↻ |
| DEPLOYMENT_VALIDATION.md | ✅ | ↻ | ↻ |
| ROADMAP_v1.0_to_v1.1.md | ✅ | ✅ | ↻ |
| IMPLEMENTATION_SUMMARY.md | ✅ | ↻ | ↻ |
| PROJECT_STATUS.md | ✅ | ✅ | ✅ |

Legend: ✅ = Complete, ↻ = Minor updates expected, - = Not yet

---

## Latest Updates

**2025-01-31**: v0.1 Foundation complete
- All 6 core components built and documented
- Database deployed with 20 historical events
- Validation flow refactored and tested
- Dashboard and API endpoint functional
- 4-week deployment roadmap created

---

## Support Channels

- **Technical Documentation**: This index
- **Deployment Help**: [DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md#troubleshooting)
- **Architecture Questions**: [ROADMAP_v1.0_to_v1.1.md](ROADMAP_v1.0_to_v1.1.md)
- **Status Updates**: [PROJECT_STATUS.md](PROJECT_STATUS.md)

---

**Last Updated**: 2025-01-31  
**Current Version**: v0.1 Foundation Complete  
**Next Update**: 2025-02-06 (Post-Phase 1)

