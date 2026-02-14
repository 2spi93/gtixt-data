CREATE TABLE IF NOT EXISTS score_version (
    version_key TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    data_dictionary JSONB NOT NULL,
    weights JSONB NOT NULL,
    hierarchy JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

INSERT INTO score_version (version_key, description, data_dictionary, weights, hierarchy, is_active)
VALUES (
    'v1.0',
    'GPTI Scoring v1.0 — modèle institutionnel (5 piliers), déterministe, NA neutre, audit-friendly.',
    '{
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
            "A_transparency": {
                "description": "Transparence des conditions de paiement",
                "metrics": {
                    "payout.delay_days": {
                        "bins": [0, 7, 14, 30, 60],
                        "labels": ["immediate", "week", "fortnight", "month", "delayed"],
                        "weights": [1.0, 0.9, 0.7, 0.5, 0.3]
                    },
                    "payout.conditions_text_quality": {
                        "bins": [0, 0.3, 0.6, 0.8, 1.0],
                        "labels": ["poor", "basic", "good", "excellent", "perfect"],
                        "weights": [0.2, 0.5, 0.7, 0.9, 1.0]
                    }
                }
            },
            "B_payout_reliability": {
                "description": "Fiabilité des paiements",
                "metrics": {
                    "rules.page_quality": {
                        "bins": [0, 0.3, 0.6, 0.8, 1.0],
                        "labels": ["poor", "basic", "good", "excellent", "perfect"],
                        "weights": [0.2, 0.5, 0.7, 0.9, 1.0]
                    },
                    "rules.length_signal": {
                        "bins": [0, 100, 500, 1000, 2000],
                        "labels": ["minimal", "short", "medium", "long", "comprehensive"],
                        "weights": [0.3, 0.6, 0.8, 0.9, 1.0]
                    }
                }
            },
            "C_risk_model": {
                "description": "Modèle de risque",
                "metrics": {
                    "legal.company_registry_country": {
                        "type": "jurisdiction_lookup",
                        "matrix": "jurisdiction_matrix_v1"
                    }
                }
            },
            "D_legal_compliance": {
                "description": "Conformité légale",
                "metrics": {
                    "reviews.sentiment_score": {
                        "bins": [0, 0.2, 0.4, 0.6, 0.8],
                        "labels": ["very_negative", "negative", "neutral", "positive", "very_positive"],
                        "weights": [0.1, 0.3, 0.5, 0.8, 1.0]
                    }
                }
            },
            "E_reputation_support": {
                "description": "Réputation et support",
                "metrics": {
                    "support.quality": {
                        "bins": [0, 0.3, 0.6, 0.8, 1.0],
                        "labels": ["poor", "basic", "good", "excellent", "perfect"],
                        "weights": [0.2, 0.5, 0.7, 0.9, 1.0]
                    }
                }
            }
        }
    }'::jsonb,
    '{
        "A_transparency": 0.25,
        "B_payout_reliability": 0.25,
        "C_risk_model": 0.20,
        "D_legal_compliance": 0.20,
        "E_reputation_support": 0.10
    }'::jsonb,
    '{
        "payout.delay_days": ["payout.conditions_delay_hint","payout.conditions_text_quality"],
        "rules.clarity": ["rules.page_quality","rules.length_signal"],
        "legal.jurisdiction": ["legal.company_registry_country"],
        "reviews.trust_score": ["reviews.sentiment_score","support.quality"]
    }'::jsonb,
    true
)
ON CONFLICT (version_key) DO UPDATE SET
    description = EXCLUDED.description,
    data_dictionary = EXCLUDED.data_dictionary,
    weights = EXCLUDED.weights,
    hierarchy = EXCLUDED.hierarchy,
    is_active = EXCLUDED.is_active;

CREATE TABLE IF NOT EXISTS snapshot_scores (
    snapshot_id INTEGER NOT NULL REFERENCES snapshot_metadata(id),
    firm_id TEXT NOT NULL,
    score JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (snapshot_id, firm_id)
);