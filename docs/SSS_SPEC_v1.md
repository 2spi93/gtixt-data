# GTIXT — Stress Scenario Simulation (SSS)
Specification v1.0

## 1. Definition
Stress Scenario Simulation (SSS) measures structural resilience to exogenous shocks, without simulating PnL or markets.

We do NOT simulate trades.
We simulate regulatory, operational, and structural shocks.

Comparable to bank stress tests (EBA/Fed), adapted to prop trading.

## 2. Strategic Objective
- Evaluate model robustness
- Identify firms fragile to change
- Provide a pre-regulatory tool for institutions

## 3. Scenarios v1.0
### S1 — Regulatory Shock
- partial CFD bans
- leverage restrictions
- offshore marketing restrictions

Inputs:
- Jurisdictional Risk Tier
- Regulatory Exposure Map
- Model Archetype

### S2 — Rule Tightening
- lower max loss
- stricter payout rules
- reduced drawdown

Inputs:
- RVI
- Rule Ambiguity
- Model Integrity

### S3 — Operational Disruption
- website downtime
- abrupt pricing change
- FAQ / T&C modifications

Inputs:
- Operational Footprint
- Data Transparency
- RVI

## 4. Calculation (v1.0)
Each scenario outputs an impact score in [0,1].

Scenario Impact = f(model_type, REM, RVI, Integrity, Transparency)

Final score:
SSS = 1 - avg(impact_s1, impact_s2, impact_s3)

## 5. Interpretation
| SSS | Resilience |
|---|---|
| < 0.30 | Very fragile |
| 0.30–0.50 | Fragile |
| 0.50–0.70 | Moderately resilient |
| 0.70–0.85 | Resilient |
| > 0.85 | Highly resilient |

## 6. Output JSON
```json
{
  "stress_simulation": {
    "score": 0.62,
    "scenarios": {
      "regulatory_shock": 0.55,
      "rule_tightening": 0.60,
      "operational_disruption": 0.71
    },
    "label": "Moderately resilient",
    "confidence": "medium"
  }
}
```

## 7. Access Tiers
| Tier | Access |
|---|---|
| Public | label |
| Pro | score + scenarios |
| Internal | inputs + matrices |
