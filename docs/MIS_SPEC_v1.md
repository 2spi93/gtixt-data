# GTIXT — Model Integrity Score (MIS)
Specification v1.0

## 1. Definition
Model Integrity Score (MIS) measures internal coherence of a prop firm’s economic model.

MIS is structural and cannot be faked without the GTIXT pipeline.

## 2. Strategic Objective
Detect:
- contradictions
- inconsistencies
- rule bricolage

Separate:
- serious models
- opportunistic models

MIS = engineering quality of the model.

## 3. Axes
| Axis | Description |
|---|---|
| Rule Consistency | rules without contradictions |
| Rule ↔ Pricing Alignment | economic logic |
| Stability | absence of erratic changes |
| Clarity | low ambiguity |
| Historical Coherence | continuity over time |

## 4. Calculation
MIS = avg(
  rule_consistency,
  pricing_alignment,
  stability,
  clarity,
  historical_coherence
)

Each sub-score ∈ [0,1].

## 5. Interpretation
| MIS | Reading |
|---|---|
| < 0.40 | Incoherent model |
| 0.40–0.60 | Fragile |
| 0.60–0.80 | Solid |
| > 0.80 | Very solid |

## 6. Output JSON
```json
{
  "model_integrity": {
    "score": 0.74,
    "components": {
      "rule_consistency": 0.80,
      "pricing_alignment": 0.70,
      "stability": 0.65,
      "clarity": 0.72,
      "historical_coherence": 0.83
    },
    "confidence": "high"
  }
}
```

## 7. Access Tiers
| Tier | Access |
|---|---|
| Public | score |
| Pro | score + components |
| Internal | evidence + diffs |
