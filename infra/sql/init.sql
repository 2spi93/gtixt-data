BEGIN;

-- 1) insère / met à jour v1.0
INSERT INTO score_version (version_key, description, data_dictionary, weights, hierarchy, is_active)
VALUES (
  'v1.0',
  'GPTI Scoring v1.0 — modèle institutionnel (5 piliers), déterministe, NA neutre, audit-friendly.',
  $${
    "schema_version": "gpti.score.v1",
    "global_formula": "score = 100 * sum_p( weight_p * pillar_score_p )",
    "na_policy": {
      "na_value": 0.5,
      "pillar_na_rate_review_threshold": 0.45,
      "firm_na_rate_review_threshold": 0.40
    },
    "jurisdiction_matrix_v1": {
      "LOW_RISK": {
        "US": 1.0, "UK": 1.0, "DE": 0.95, "FR": 0.95, "NL": 0.95,
        "SE": 0.95, "AU": 0.95, "SG": 0.95, "JP": 0.90, "CA": 0.90
      },
      "MEDIUM_RISK": {
        "AE": 0.75, "CY": 0.70, "MT": 0.70, "EE": 0.70, "LT": 0.70,
        "PL": 0.65, "RO": 0.65, "BG": 0.60, "TR": 0.60, "ZA": 0.55
      },
      "HIGH_RISK": {
        "KY": 0.40, "VG": 0.40, "SC": 0.40, "MU": 0.40,
        "BS": 0.35, "PA": 0.35, "CR": 0.35, "IN": 0.30, "PH": 0.30, "VN": 0.30
      },
      "VERY_HIGH_RISK": {
        "RU": 0.20, "BY": 0.20, "CN": 0.20, "HK": 0.20,
        "NG": 0.15, "KE": 0.15, "TZ": 0.15,
        "UNKNOWN": 0.10, "OFFSHORE": 0.10
      }
    },
    "pillars": {
      "...": "mets ici le contenu complet, et pour les métriques binées utilise bins + labels (arrays ordonnés)"
    }
  }$$::jsonb,
  $${
    "A_transparency": 0.25,
    "B_payout_reliability": 0.25,
    "C_risk_model": 0.20,
    "D_legal_compliance": 0.20,
    "E_reputation_support": 0.10
  }$$::jsonb,
  $${
    "payout.delay_days": ["payout.conditions_delay_hint","payout.conditions_text_quality"],
    "rules.clarity": ["rules.page_quality","rules.length_signal"],
    "legal.jurisdiction": ["legal.company_registry_country"],
    "reviews.trust_score": ["reviews.sentiment_score","support.quality"]
  }$$::jsonb,
  true
)
ON CONFLICT (version_key) DO UPDATE SET
  description = EXCLUDED.description,
  data_dictionary = EXCLUDED.data_dictionary,
  weights = EXCLUDED.weights,
  hierarchy = EXCLUDED.hierarchy,
  is_active = EXCLUDED.is_active;

-- 2) garantit qu'il n'y a qu'une seule version active
UPDATE score_version
SET is_active = false
WHERE version_key <> 'v1.0';

COMMIT;
