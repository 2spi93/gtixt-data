-- Agent C audit trail (IOSCO-friendly)
CREATE TABLE IF NOT EXISTS agent_c_audit (
  snapshot_key text NOT NULL,
  firm_id      text NOT NULL,
  version_key  text NOT NULL,
  verdict      text NOT NULL CHECK (verdict IN ('pass','review')),
  confidence   text NOT NULL,
  na_rate      numeric NOT NULL,
  reasons      jsonb NOT NULL,           -- deterministic reasons
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (snapshot_key, firm_id, version_key)
);

-- View: only firms approved by Agent C for publication
CREATE OR REPLACE VIEW publishable_firms AS
SELECT s.snapshot_key, s.firm_id, s.version_key, s.score_0_100, s.pillar_scores, s.metric_scores, s.na_rate, s.confidence, a.reasons
FROM snapshot_scores s
JOIN agent_c_audit  a
  ON a.snapshot_key=s.snapshot_key AND a.firm_id=s.firm_id AND a.version_key=s.version_key
WHERE a.verdict='pass';