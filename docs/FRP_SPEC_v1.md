# GTIXT — Future Risk Projection (FRP)
Specification v1.0

## 1. Definition
Future Risk Projection (FRP) is a deterministic projection of future structural risk based on observed history.

This is NOT a bankruptcy prediction.
It is a risk trajectory.

## 2. Strategic Objective
- Provide forward-looking visibility
- Identify rising-risk firms
- Support funds, partners, and institutional traders

## 3. Key Inputs
| Source | Role |
|---|---|
| RVI | instability |
| REM | regulatory exposure |
| MIS | model quality |
| Survivability | longevity |
| Institutional Readiness | maturity |
| Score trends | drift |

## 4. Calculation (v1.0)
FRP = f(
  slope(score_history),
  RVI,
  REM,
  MIS_inverse,
  survivability_inverse
)

Projection horizons:
- 3 months
- 6 months
- 12 months

## 5. Output JSON
```json
{
  "future_risk_projection": {
    "3m": 0.42,
    "6m": 0.55,
    "12m": 0.68,
    "trajectory": "increasing",
    "risk_level": "moderate_to_high",
    "confidence": "medium"
  }
}
```

## 6. Interpretation
| FRP | Reading |
|---|---|
| < 0.30 | Stable |
| 0.30–0.50 | Moderate |
| 0.50–0.70 | High |
| > 0.70 | Critical |

## 7. Access Tiers
| Tier | Access |
|---|---|
| Public | label |
| Pro | curve |
| Internal | drivers + matrices |
