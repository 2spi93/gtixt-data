# GTIXT — Institutional Readiness Score (IRS)
Specification v1.0

## 1. Definition
Institutional Readiness Score (IRS) measures the maturity of a prop firm to interact with institutional actors, platforms, partners, investors, or financial infrastructures.

IRS ≠ performance
IRS ≠ popularity
IRS = institutional compatibility

## 2. Strategic Objective
- Identify institution-ready firms
- Separate retail-oriented vs semi-pro vs institution-grade
- Prepare partnerships, integrations, listings, and future tokenization

## 3. Pillars
| Pillar | Description |
|---|---|
| Governance Maturity | structure & transparency |
| Legal Clarity | legal quality |
| Operational Discipline | stability & rigor |
| Data Transparency | public data quality |
| Compliance Compatibility | regulatory compatibility |

## 4. Decomposition & Weights
IRS = Σ(pillar_score × weight)

| Pillar | Weight |
|---|---|
| Governance Maturity | 0.25 |
| Legal Clarity | 0.20 |
| Operational Discipline | 0.20 |
| Data Transparency | 0.20 |
| Compliance Compatibility | 0.15 |

## 5. Pillar Details
### Governance Maturity
Inputs:
- clear T&C
- visible versioning
- rules ↔ pricing coherence
- structured official communications

Score increases with stable rules, traceable history, and no contradictions.

### Legal Clarity
Inputs:
- explicit jurisdiction
- complete disclaimers
- defined responsibility
- absence of ambiguous clauses

Linked to REM and Rule Ambiguity Heatmap.

### Operational Discipline
Inputs:
- inverse RVI
- stability of rules
- modification frequency
- anomaly management

### Data Transparency
Inputs:
- rules/FAQ availability
- pricing clarity
- usable metrics
- low NA rate

### Compliance Compatibility
Inputs:
- Jurisdictional Risk Tier
- Regulatory Exposure Map
- model ↔ regulated-zone compatibility

## 6. Interpretation
| Score | Reading |
|---|---|
| 0.00–0.30 | Retail-grade |
| 0.30–0.50 | Semi-professional |
| 0.50–0.70 | Emerging institutional |
| 0.70–0.85 | Institutional-ready |
| 0.85–1.00 | Institution-grade |

## 7. Snapshot Output (JSON)
```json
{
  "institutional_readiness": {
    "score": 0.68,
    "label": "Emerging institutional",
    "pillars": {
      "governance": 0.72,
      "legal_clarity": 0.65,
      "operational_discipline": 0.60,
      "data_transparency": 0.75,
      "compliance_compatibility": 0.68
    },
    "confidence": "high"
  }
}
```

## 8. Access Tiers
| Tier | Access |
|---|---|
| Public | label |
| Pro | score + pillars |
| Internal | detailed inputs |

## 9. Extensions
v2:
- partner mapping
- readiness by region

v3:
- token-compatible readiness
- clearing / settlement readiness
