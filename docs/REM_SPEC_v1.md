# GTIXT — Regulatory Exposure Map (REM)
Specification v1.0

## 1. Definition
Regulatory Exposure Map (REM) measures structural regulatory exposure by combining:
- operating jurisdictions
- client jurisdictions
- public regulatory mentions
- model risk vs legal frameworks

REM ≠ legal compliance
REM = exposure to regulatory risk

## 2. Institutional Objective
- Identify regulatory fragility zones
- Anticipate legal rupture points
- Deliver geopolitical + regulatory visibility
- Provide a unique tool for investors & compliance

## 3. Data Sources (Public Only)
Jurisdictions analyzed:
- legal entity registration
- countries mentioned in T&C
- explicitly accepted/blocked client countries
- infrastructure location (servers/CDN)

Regulatory signals:
- ESMA warnings
- FCA notices
- ASIC publications
- AMF alerts
- other recognized authorities

No private data. No allegations. No opinions.

## 4. Exposure Dimensions (REM Core)
REM is a matrix, not a single score.

| Axis | Description |
|---|---|
| Registration | registration country |
| Client Reach | countries where clients are accepted |
| Regulatory Mentions | authority citations |
| Model Risk | model ↔ legal compatibility |
| Jurisdiction Stability | legal stability |

## 5. Jurisdiction Tiering
GTIXT proprietary tiers:

| Tier | Description |
|---|---|
| 1 | clear, stable regulation |
| 2 | partial regulation |
| 3 | gray zone |
| 4 | high uncertainty |
| 5 | high risk |

Based on clarity, enforcement history, stability, jurisprudence.

## 6. REM Score v1.0
Component weights:

| Component | Weight |
|---|---|
| Registration Risk | 0.30 |
| Client Jurisdiction Risk | 0.25 |
| Regulatory Mentions | 0.25 |
| Model Compatibility | 0.20 |

REM_score = Σ(component_score × weight), normalized to [0, 1].

## 7. Snapshot Output (JSON)
```json
{
  "regulatory_exposure": {
    "score": 0.67,
    "tier": "High exposure",
    "map": [
      {
        "country": "EU",
        "tier": 2,
        "signal": "High exposure: ESMA zone"
      },
      {
        "country": "AU",
        "tier": 1,
        "signal": "Moderate exposure: ASIC jurisdiction"
      }
    ],
    "regulatory_mentions": [
      {
        "authority": "FCA",
        "type": "warning",
        "date": "2025-09-12"
      }
    ],
    "confidence": "medium"
  }
}
```

## 8. Access Tiers
| Tier | Access |
|---|---|
| Public | global tier + simplified map |
| Pro | per-country details |
| Internal | logs + sources |

## 9. Extensions
v2:
- interactive heatmap
- regulatory timeline
- correlation with RVI

v3:
- regulatory stress simulation
- geopolitical projection
- pre-ESMA/pre-FCA signals
