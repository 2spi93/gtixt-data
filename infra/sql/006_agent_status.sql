CREATE TABLE IF NOT EXISTS agent_status (
  agent TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('complete', 'testing', 'pending')),
  evidence_types JSONB NOT NULL DEFAULT '[]'::jsonb,
  performance_ms INTEGER NOT NULL DEFAULT 0,
  last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO agent_status (agent, name, description, status, evidence_types, performance_ms)
VALUES
  ('CRAWLER', 'Web Crawler', 'Collecte des pages publiques (rules, pricing, legal, FAQ)', 'testing', '["RAW_HTML","HOME_HTML","RULES_HTML","PRICING_HTML"]', 0),
  ('RVI', 'Registry Verification', 'Verification des licences et registres reglementaires (FCA, FINRA, etc.)', 'testing', '["LICENSE_VERIFICATION"]', 0),
  ('SSS', 'Sanctions Screening', 'Depistage des listes de sanctions (OFAC, ONU, EU, etc.)', 'testing', '["WATCHLIST_MATCH"]', 0),
  ('REM', 'Regulatory Events Monitor', 'Suivi des actions reglementaires et violations de conformite', 'testing', '["REGULATORY_EVENT"]', 0),
  ('IRS', 'Independent Review System', 'Validation des soumissions et documents reglementaires', 'testing', '["SUBMISSION_VERIFICATION"]', 0),
  ('FRP', 'Firm Reputation & Payout', 'Analyse de la reputation, des paiements et des sentiments', 'testing', '["REPUTATION_RISK","PAYOUT_RISK","SENTIMENT_RISK"]', 0),
  ('MIS', 'Manual Investigation System', 'Recherche approfondie et detection d''anomalies', 'testing', '["DOMAIN_ANOMALY","COMPANY_ISSUE","NEWS_RISK","SUSPICIOUS_PATTERN"]', 0),
  ('IIP', 'IOSCO Implementation & Publication', 'Generation de rapports de conformite IOSCO et certification reglementaire', 'testing', '["COMPLIANCE_REPORT"]', 0),
  ('AGENT_C', 'Oversight Gate', 'Controle qualite, validation finale, publication snapshots', 'testing', '["VALIDATION_EVENT","SNAPSHOT_APPROVAL"]', 0)
ON CONFLICT (agent) DO NOTHING;

WITH evidence_counts AS (
  SELECT collected_by AS agent_key, COUNT(*)::int AS evidence_count
  FROM evidence_collection
  GROUP BY collected_by
),
validation_counts AS (
  SELECT COUNT(*)::int AS validation_count
  FROM validation_metrics
)
UPDATE agent_status a
SET status = CASE
    WHEN a.agent = 'AGENT_C' AND (SELECT validation_count FROM validation_counts) > 0 THEN 'complete'
    WHEN a.agent <> 'AGENT_C' AND COALESCE(evidence_counts.evidence_count, 0) > 0 THEN 'complete'
    ELSE 'testing'
  END,
  last_updated = NOW()
FROM evidence_counts
WHERE a.agent = evidence_counts.agent_key OR a.agent = 'AGENT_C';
