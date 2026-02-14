-- GPTI Sanctions Database Schema
-- PostgreSQL schema for OFAC and UN sanctions data
-- Version: 1.0.0
-- Created: February 1, 2026

-- Drop existing tables if they exist
DROP TABLE IF EXISTS firm_snapshots CASCADE;
DROP TABLE IF EXISTS sanctions_matches CASCADE;
DROP TABLE IF EXISTS sanctions_entities CASCADE;
DROP TABLE IF EXISTS sanctions_lists CASCADE;

-- Firm Snapshots Table - Tracks historical scores and metrics
CREATE TABLE firm_snapshots (
  id SERIAL PRIMARY KEY,
  
  -- Firm identification
  firm_id VARCHAR(100) NOT NULL,
  firm_name VARCHAR(500) NOT NULL,
  
  -- Score data
  score NUMERIC(5,2), -- Score 0-100
  score_normalized NUMERIC(5,4), -- Score 0.0-1.0
  integrity_score NUMERIC(5,2),
  confidence VARCHAR(50), -- 'high', 'medium', 'low'
  
  -- Percentiles
  percentile_overall NUMERIC(5,2),
  percentile_model NUMERIC(5,2),
  percentile_jurisdiction NUMERIC(5,2),
  
  -- Pillar scores (pillars as JSONB)
  pillar_scores JSONB, -- {A_transparency: 85, B_payout_reliability: 92, ...}
  
  -- Metrics (flexible storage)
  metrics JSONB, -- {na_rate: 0.05, rule_changes_frequency: 'monthly', ...}
  
  -- Status & metadata
  status VARCHAR(50), -- 'candidate', 'ranked', 'excluded'
  oversight_gate_verdict VARCHAR(50),
  audit_verdict VARCHAR(50),
  
  -- Snapshot reference
  snapshot_id VARCHAR(200), -- Links to specific GTIXT snapshot
  snapshot_hash VARCHAR(64), -- SHA-256 of snapshot
  
  -- Timestamps
  captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), -- When score was valid
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  -- Indexing
  INDEX idx_firm_snapshots_firm_id_captured (firm_id, captured_at DESC),
  INDEX idx_firm_snapshots_captured (captured_at DESC),
  UNIQUE(firm_id, snapshot_id)
);

-- Create sanctions lists table (OFAC, UN, etc.)
CREATE TABLE sanctions_lists (
  id SERIAL PRIMARY KEY,
  list_name VARCHAR(100) NOT NULL UNIQUE, -- 'OFAC_SDN', 'UN_CONSOLIDATED'
  source_url TEXT NOT NULL,
  last_updated TIMESTAMP WITH TIME ZONE,
  record_count INTEGER DEFAULT 0,
  checksum VARCHAR(64), -- SHA-256 of source file
  status VARCHAR(20) DEFAULT 'active', -- active, updating, error
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create sanctions entities table (main data)
CREATE TABLE sanctions_entities (
  id SERIAL PRIMARY KEY,
  list_id INTEGER NOT NULL REFERENCES sanctions_lists(id) ON DELETE CASCADE,
  
  -- Entity identification
  entity_id VARCHAR(100) NOT NULL, -- OFAC UID or UN reference number
  entity_type VARCHAR(50) NOT NULL, -- 'individual', 'entity', 'vessel', 'aircraft'
  
  -- Names (multiple variations)
  primary_name VARCHAR(500) NOT NULL,
  name_variants TEXT[], -- Array of alternative names
  name_normalized VARCHAR(500), -- Lowercase, no special chars
  
  -- Sanctions program
  program VARCHAR(200), -- e.g., 'UKRAINE-EO13662', 'AL-QAIDA'
  sanctions_list VARCHAR(100) NOT NULL, -- 'SDN', 'FSE', 'NONSDN', etc.
  
  -- Additional details
  title VARCHAR(200), -- For individuals (Dr., Mr., etc.)
  remarks TEXT, -- Additional information
  nationality VARCHAR(100)[], -- Array of countries
  date_of_birth DATE,
  place_of_birth VARCHAR(200),
  
  -- Address information
  addresses JSONB, -- Array of address objects
  
  -- Identification documents
  identification_docs JSONB, -- Passports, IDs, etc.
  
  -- Timestamps
  added_date DATE, -- When entity was added to sanctions list
  last_modified TIMESTAMP WITH TIME ZONE,
  
  -- Metadata
  raw_data JSONB, -- Original data for reference
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  -- Ensure unique entity per list
  UNIQUE(list_id, entity_id)
);

-- Create sanctions matches table (screening results)
CREATE TABLE sanctions_matches (
  id SERIAL PRIMARY KEY,
  
  -- Search details
  search_name VARCHAR(500) NOT NULL,
  search_type VARCHAR(50) NOT NULL, -- 'exact', 'fuzzy', 'phonetic'
  
  -- Match details
  entity_id INTEGER NOT NULL REFERENCES sanctions_entities(id) ON DELETE CASCADE,
  similarity_score NUMERIC(5,4), -- 0.0000 to 1.0000
  match_reason VARCHAR(100), -- 'exact_match', 'name_variant', 'fuzzy_match'
  
  -- Match metadata
  matched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  matched_by VARCHAR(100), -- System/user who performed search
  
  -- Result
  screening_status VARCHAR(50) NOT NULL, -- 'SANCTIONED', 'POTENTIAL_MATCH', 'REVIEW_REQUIRED'
  
  -- Audit trail
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_entities_primary_name ON sanctions_entities(primary_name);
CREATE INDEX idx_entities_normalized ON sanctions_entities(name_normalized);
CREATE INDEX idx_entities_entity_type ON sanctions_entities(entity_type);
CREATE INDEX idx_entities_program ON sanctions_entities(program);
CREATE INDEX idx_entities_list_id ON sanctions_entities(list_id);
CREATE INDEX idx_entities_added_date ON sanctions_entities(added_date);

-- GIN indexes for arrays and JSONB
CREATE INDEX idx_entities_name_variants ON sanctions_entities USING GIN(name_variants);
CREATE INDEX idx_entities_nationality ON sanctions_entities USING GIN(nationality);
CREATE INDEX idx_entities_addresses ON sanctions_entities USING GIN(addresses);
CREATE INDEX idx_entities_raw_data ON sanctions_entities USING GIN(raw_data);

-- Full-text search index
CREATE INDEX idx_entities_name_fts ON sanctions_entities USING GIN(
  to_tsvector('english', primary_name || ' ' || COALESCE(array_to_string(name_variants, ' '), ''))
);

-- Indexes for matches table
CREATE INDEX idx_matches_search_name ON sanctions_matches(search_name);
CREATE INDEX idx_matches_entity_id ON sanctions_matches(entity_id);
CREATE INDEX idx_matches_matched_at ON sanctions_matches(matched_at);
CREATE INDEX idx_matches_screening_status ON sanctions_matches(screening_status);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_sanctions_lists_updated_at
  BEFORE UPDATE ON sanctions_lists
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sanctions_entities_updated_at
  BEFORE UPDATE ON sanctions_entities
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Insert initial sanctions lists
INSERT INTO sanctions_lists (list_name, source_url, status) VALUES
  ('OFAC_SDN', 'https://www.treasury.gov/ofac/downloads/sdn.csv', 'active'),
  ('UN_CONSOLIDATED', 'https://scsanctions.un.org/resources/xml/en/consolidated.xml', 'active');

-- Create view for active sanctions
CREATE VIEW active_sanctions AS
SELECT 
  e.id,
  e.entity_id,
  e.entity_type,
  e.primary_name,
  e.name_variants,
  e.program,
  e.sanctions_list,
  e.nationality,
  e.added_date,
  l.list_name,
  l.last_updated AS list_last_updated
FROM sanctions_entities e
JOIN sanctions_lists l ON e.list_id = l.id
WHERE l.status = 'active';

-- Create view for sanctions statistics
CREATE VIEW sanctions_statistics AS
SELECT 
  l.list_name,
  l.last_updated,
  COUNT(e.id) AS total_entities,
  COUNT(CASE WHEN e.entity_type = 'individual' THEN 1 END) AS individuals,
  COUNT(CASE WHEN e.entity_type = 'entity' THEN 1 END) AS entities,
  COUNT(DISTINCT e.program) AS programs,
  COUNT(DISTINCT e.sanctions_list) AS lists
FROM sanctions_lists l
LEFT JOIN sanctions_entities e ON l.id = e.list_id
WHERE l.status = 'active'
GROUP BY l.id, l.list_name, l.last_updated;

-- Grant permissions (adjust as needed)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gpti_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gpti_app;

-- Comments for documentation
COMMENT ON TABLE sanctions_lists IS 'Tracks different sanctions lists (OFAC, UN, etc.)';
COMMENT ON TABLE sanctions_entities IS 'Stores sanctioned entities with all their details';
COMMENT ON TABLE sanctions_matches IS 'Records screening matches for audit trail';
COMMENT ON COLUMN sanctions_entities.name_variants IS 'Alternative spellings and aliases';
COMMENT ON COLUMN sanctions_entities.name_normalized IS 'Normalized for faster matching';
COMMENT ON COLUMN sanctions_matches.similarity_score IS 'Fuzzy match score (0-1)';
