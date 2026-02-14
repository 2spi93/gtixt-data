# GTIXT — Survivability Score (SS)
Specification v1.0

## 1. Definition
Survivability Score (SS) estimates structural ability of a prop firm to persist over time, independent of current popularity.

SS ≠ reputation
SS ≠ profitability
SS = structural resilience

## 2. Institutional Objective
- Identify fragile models
- Anticipate firm exits
- Provide long-term viability signal
- Protect investors & traders

## 3. Dimensions
| Dimension | Description |
|---|---|
| Operational Stability | rule stability |
| Regulatory Resilience | exposure to regulatory risk |
| Economic Coherence | pricing ↔ rules consistency |
| Infrastructure Robustness | tech/domains reliability |
| Historical Consistency | stability over time |

## 4. Score Decomposition
SS = Σ(dimension_score × weight)

| Dimension | Weight |
|---|---|
| Operational Stability (1 - RVI) | 0.25 |
| Regulatory Resilience (1 - REM) | 0.25 |
| Economic Coherence | 0.20 |
| Infrastructure Robustness | 0.15 |
| Historical Consistency | 0.15 |

## 5. Key Calculations
Example:
- RVI = 0.72 → Stability = 0.28
- REM = 0.67 → Resilience = 0.33

SS ≈ 0.25×0.28 + 0.25×0.33 + ...

## 6. Interpretation
| Score | Reading |
|---|---|
| 0.00–0.30 | Low survivability |
| 0.30–0.50 | Fragile |
| 0.50–0.70 | Moderate |
| 0.70–0.85 | Solid |
| 0.85–1.00 | Highly resilient |

## 7. Snapshot Output (JSON)
```json
{
  "survivability": {
    "score": 0.42,
    "label": "Fragile",
    "drivers": {
      "operational_stability": 0.28,
      "regulatory_resilience": 0.33,
      "economic_coherence": 0.55,
      "infrastructure": 0.70,
      "historical_consistency": 0.60
    },
    "projection_12m": "at risk",
    "confidence": "medium"
  }
}
```

## 8. NA & Safeguards
- NA → neutral (0.5)
- Excess NA → confidence ↓
- Agent C override allowed with audit trail

## 9. Access Tiers
| Tier | Access |
|---|---|
| Public | label only |
| Pro | score + drivers |
| Internal | projection + logs |

## 10. Positioning
Survivability Score = longevity rating for prop firms (credit-outlook equivalent).
