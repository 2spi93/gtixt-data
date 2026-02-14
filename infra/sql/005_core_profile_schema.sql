-- Core schema for firm profiles, snapshots, and agent data
-- Safe to run multiple times

BEGIN;

-- Base firms table (extend if already exists)
CREATE TABLE IF NOT EXISTS firms (
  id SERIAL PRIMARY KEY,
  firm_id TEXT UNIQUE,
  name TEXT,
  brand_name TEXT,
  website_root TEXT,
  model_type TEXT,
  status TEXT,
  fca_reference TEXT,
  jurisdiction TEXT,
  jurisdiction_tier TEXT,
  logo_url TEXT,
  founded_year INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE firms ADD COLUMN IF NOT EXISTS firm_id TEXT;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS brand_name TEXT;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS website_root TEXT;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS model_type TEXT;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS status TEXT;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS fca_reference TEXT;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS jurisdiction TEXT;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS jurisdiction_tier TEXT;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS logo_url TEXT;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS founded_year INTEGER;
ALTER TABLE firms ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE firms ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Ensure firm_id values exist
UPDATE firms
SET firm_id = LOWER(REGEXP_REPLACE(COALESCE(brand_name, name, ''), '[^a-z0-9]+', '-', 'g'))
WHERE firm_id IS NULL OR firm_id = '';

-- Replace empty or invalid slug with fallback
UPDATE firms
SET firm_id = 'firm-' || id
WHERE firm_id IS NULL OR firm_id = '' OR firm_id = '-';

-- De-duplicate firm_id values
WITH dupes AS (
  SELECT id, firm_id,
         ROW_NUMBER() OVER (PARTITION BY firm_id ORDER BY id) AS rn
  FROM firms
)
UPDATE firms f
SET firm_id = f.firm_id || '-' || f.id
FROM dupes d
WHERE f.id = d.id AND d.rn > 1;

-- Backfill brand_name
UPDATE firms
SET brand_name = COALESCE(brand_name, name)
WHERE brand_name IS NULL;

-- Backfill website_root from fca_reference when it looks like a URL
UPDATE firms
SET website_root = COALESCE(website_root, fca_reference)
WHERE (website_root IS NULL OR website_root = '')
  AND (fca_reference ILIKE 'http%');

CREATE UNIQUE INDEX IF NOT EXISTS idx_firms_firm_id ON firms(firm_id);
CREATE INDEX IF NOT EXISTS idx_firms_status ON firms(status);
CREATE INDEX IF NOT EXISTS idx_firms_updated_at ON firms(updated_at DESC);

-- Firm profile (agent-enriched fields)
CREATE TABLE IF NOT EXISTS firm_profiles (
  firm_id TEXT PRIMARY KEY REFERENCES firms(firm_id) ON DELETE CASCADE,
  executive_summary TEXT,
  status_gtixt TEXT,
  data_sources JSONB,
  verification_hash TEXT,
  last_updated TIMESTAMPTZ,
  audit_verdict TEXT,
  oversight_gate_verdict TEXT,
  extra JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Evidence (used by db.py)
CREATE TABLE IF NOT EXISTS evidence (
  id SERIAL PRIMARY KEY,
  firm_id TEXT NOT NULL,
  key TEXT NOT NULL,
  source_url TEXT,
  sha256 TEXT NOT NULL,
  excerpt TEXT,
  raw_object_path TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (firm_id, key, sha256)
);

CREATE INDEX IF NOT EXISTS idx_evidence_firm_id ON evidence(firm_id);
CREATE INDEX IF NOT EXISTS idx_evidence_key ON evidence(key);

-- Datapoints (agent outputs)
CREATE TABLE IF NOT EXISTS datapoints (
  id SERIAL PRIMARY KEY,
  firm_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json JSONB,
  value_text TEXT,
  source_url TEXT,
  evidence_hash TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_datapoints_firm_key ON datapoints(firm_id, key);
CREATE INDEX IF NOT EXISTS idx_datapoints_created_at ON datapoints(created_at DESC);

-- Snapshot metadata
CREATE TABLE IF NOT EXISTS snapshot_metadata (
  id SERIAL PRIMARY KEY,
  snapshot_key TEXT NOT NULL,
  bucket TEXT NOT NULL,
  object TEXT NOT NULL,
  sha256 TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshot_metadata_created_at ON snapshot_metadata(created_at DESC);

-- Snapshot scores (agent C gated)
CREATE TABLE IF NOT EXISTS snapshot_scores (
  snapshot_id INTEGER NOT NULL REFERENCES snapshot_metadata(id) ON DELETE CASCADE,
  firm_id TEXT NOT NULL,
  snapshot_key TEXT,
  version_key TEXT,
  score JSONB,
  score_0_100 NUMERIC,
  pillar_scores JSONB,
  metric_scores JSONB,
  na_rate NUMERIC,
  confidence TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (snapshot_id, firm_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_scores_firm_id ON snapshot_scores(firm_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_scores_created_at ON snapshot_scores(created_at DESC);

-- Snapshot audit
CREATE TABLE IF NOT EXISTS snapshot_audit (
  id SERIAL PRIMARY KEY,
  snapshot_id INTEGER NOT NULL REFERENCES snapshot_metadata(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMIT;
