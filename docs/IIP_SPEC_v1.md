# GTIXT — Index Inclusion Probability (IIP)
Specification v1.0

## 1. Definition
Index Inclusion Probability (IIP) estimates the likelihood that a prop firm is included (or maintained) in the GTIXT index, based on deterministic index rules.

IIP ≠ subjective score
IIP = conditional probability based on index criteria

## 2. Institutional Objective
- Anticipate index entries/exits
- Signal potential downgrades or exclusions
- Provide forward-looking, non-financial outlook

## 3. Primary Inputs
| Source | Role |
|---|---|
| Global score | structural performance |
| NA rate | data quality |
| Agent C verdict | coherence / quality |
| Survivability Score | longevity |
| Institutional Readiness | maturity |
| REM | regulatory exposure |
| RVI | stability |

## 4. Model (v1.0)
Raw score:
IIP_raw = w1×Score_norm
        + w2×Survivability
        + w3×InstitutionalReadiness
        + w4×(1 - REM)
        + w5×(1 - RVI)

Deterministic adjustments:
| Condition | Impact |
|---|---|
| Agent C = review | −0.30 |
| NA rate > 40% | −0.25 |
| Regulatory Tier 5 | −0.40 |
| Data inconsistency | −0.20 |

Clamp final to [0, 1].

## 5. Weights v1.0
| Component | Weight |
|---|---|
| Global score | 0.30 |
| Survivability | 0.20 |
| Institutional Readiness | 0.20 |
| Regulatory Safety | 0.20 |
| Stability (1 - RVI) | 0.10 |

## 6. Interpretation
| IIP | Reading |
|---|---|
| 0.00–0.25 | Very low |
| 0.25–0.45 | Low |
| 0.45–0.65 | Moderate |
| 0.65–0.85 | High |
| 0.85–1.00 | Very high |

## 7. Snapshot Output (JSON)
```json
{
  "index_inclusion_probability": {
    "probability": 0.74,
    "label": "High",
    "drivers": {
      "score": 0.68,
      "survivability": 0.55,
      "institutional_readiness": 0.68,
      "regulatory_safety": 0.33,
      "stability": 0.28
    },
    "penalties": [
      "moderate_regulatory_exposure"
    ],
    "confidence": "medium"
  }
}
```

## 8. Access Tiers
| Tier | Access |
|---|---|
| Public | label |
| Pro | probability |
| Internal | details + penalties |

## 9. Strategic Role
IIP acts as an automated index-committee outlook.
