# GTIXT — Rule Volatility Index (RVI)
Specification v1.0

## 1. Definition
Rule Volatility Index (RVI) measures historical rule stability for a prop firm by quantifying:
- change frequency
- change amplitude
- potential trader impact
- cross-document consistency over time

RVI ≠ rule quality
RVI = stability and predictability of the operational framework

## 2. Institutional Objective
- Identify structurally unstable firms
- Quantify risk of changing conditions
- Provide a pre-regulatory signal
- Deliver a neutral, non-opinionated metric

Higher RVI ⇒ higher rule volatility.

## 3. Scope
Applies to all firms indexed by GTIXT, using only:
- public rules
- written conditions
- FAQ
- crawl-detected histories

No private data. No user complaints. No payout outcomes.

## 4. Rules Coverage
Documents monitored:
- Terms & Conditions
- Rules pages
- FAQ
- Trading rules PDFs
- Updates / changelogs (if present)

Normalized rule categories:
- Risk (max daily loss, max total loss)
- Trading behavior (news trading, overnight)
- Payout (delays, thresholds)
- Evaluation (challenge steps)
- Fees (resets, subscriptions)
- Enforcement (discretion clauses)

## 5. Score Decomposition
RVI is a weighted average of four sub-scores:

RVI = (F * 0.30) + (A * 0.30) + (I * 0.25) + (C * 0.15)

| Component | Name | Weight |
|---|---|---|
| F | Frequency Score | 0.30 |
| A | Amplitude Score | 0.30 |
| I | Impact Score | 0.25 |
| C | Consistency Score | 0.15 |

## 6. Sub-scores
### A) Frequency Score (F)
Measures change frequency over 12 months.

F = min(1, changes_detected / threshold)

- changes_detected = number of unique modifications over 12 months
- threshold = 12 (1 change per month)

| Changes/Year | F |
|---|---|
| 0–1 | 0.05 |
| 2–4 | 0.20 |
| 5–8 | 0.50 |
| 9–12 | 0.75 |
| >12 | 1.00 |

### B) Amplitude Score (A)
Measures structural magnitude of changes.

Each change is classified:
- minor wording: 0.1
- clarification: 0.3
- condition modified: 0.6
- key rule modified: 0.9
- clause added/removed: 1.0

A = weighted mean of amplitudes detected.

### C) Impact Score (I)
Measures potential trader impact by affected rule area.

| Impacted Area | Impact |
|---|---|
| Fees / resets | 0.3 |
| Trading style | 0.5 |
| Risk limits | 0.8 |
| Payout conditions | 0.9 |
| Discretion clauses | 1.0 |

I = max impact detected in the window.

### D) Consistency Score (C)
Measures cross-document consistency over time.

Detects:
- contradictions (Rules vs FAQ)
- divergent definitions
- missing rules in some documents

C = contradictions_detected / total_checks, clamped to [0, 1].

## 7. Final Normalization
RVI is normalized to [0, 1].

| RVI Range | Interpretation |
|---|---|
| 0.00–0.20 | Very stable |
| 0.20–0.40 | Stable |
| 0.40–0.60 | Moderately volatile |
| 0.60–0.80 | Volatile |
| 0.80–1.00 | Highly volatile |

## 8. Snapshot Output (JSON)
```json
{
  "rvi": {
    "value": 0.72,
    "label": "High volatility",
    "components": {
      "frequency": 0.75,
      "amplitude": 0.68,
      "impact": 0.90,
      "consistency": 0.55
    },
    "window_months": 12,
    "last_change_detected": "2026-01-12",
    "confidence": "medium"
  }
}
```

## 9. NA & Fallback Policy
| Situation | Treatment |
|---|---|
| <3 snapshots | RVI = NA |
| NA | neutral score = 0.5 |
| Unconfirmed contradictions | partial penalty |
| Missing documents | confidence ↓ |

## 10. Access Tiers
| Tier | Access |
|---|---|
| Public | label only (Stable / Volatile) |
| Pro | numeric value + history |
| Internal | components + logs |

## 11. Extensions (v2 / v3)
v2:
- size-weighted adjustments
- temporal decay
- sector comparisons

v3:
- correlation with payout disputes
- stress scenario under abrupt changes
- 6–12 month internal projection

## 12. Positioning
RVI is the VIX-equivalent for prop trading rule stability:
- neutral
- auditable
- institution-ready
