-- Migration: 004_create_evidence_table.sql
-- Purpose: Evidence collection for audit trail and transparency
-- Created: 2026-02-01
-- Phase: 1 (Validation Framework)

-- Evidence table stores raw data supporting score calculations
CREATE TABLE IF NOT EXISTS evidence_collection (
    evidence_id SERIAL PRIMARY KEY,
    firm_id VARCHAR(50) NOT NULL,
    
    -- Evidence metadata
    evidence_type VARCHAR(50) NOT NULL, -- 'webpage', 'document', 'registry_entry', 'api_response', 'user_feedback'
    evidence_source VARCHAR(100) NOT NULL, -- URL or source identifier
    evidence_hash VARCHAR(64) NOT NULL, -- SHA-256 hash of evidence content
    
    -- Content storage
    content_text TEXT, -- Extracted text content
    content_json JSONB, -- Structured data (e.g., API responses)
    content_url TEXT, -- Original URL
    content_snapshot_path TEXT, -- S3 path to archived snapshot
    
    -- Attribution
    collected_by VARCHAR(50) NOT NULL, -- Agent name (e.g., 'RVI', 'REM', 'web_crawler')
    collection_method VARCHAR(50), -- 'automated_crawl', 'api_fetch', 'manual_upload', 'registry_sync'
    
    -- Relevance scoring
    relevance_score FLOAT CHECK (relevance_score >= 0 AND relevance_score <= 1),
    relevance_reason TEXT,
    
    -- Link to score calculation
    affects_metric VARCHAR(50), -- Which metric this evidence supports
    affects_score_version VARCHAR(20), -- Score version (e.g., 'v1.0')
    impact_weight FLOAT, -- How much this evidence weighted in calculation
    
    -- Verification
    is_verified BOOLEAN DEFAULT FALSE,
    verified_by VARCHAR(100),
    verified_at TIMESTAMP WITH TIME ZONE,
    verification_notes TEXT,
    
    -- Quality flags
    is_stale BOOLEAN DEFAULT FALSE, -- Data older than threshold
    is_ambiguous BOOLEAN DEFAULT FALSE, -- Requires human review
    confidence_level VARCHAR(20), -- 'high', 'medium', 'low'
    
    -- Timestamps
    collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE, -- When evidence should be re-collected
    
    -- Constraints
    CONSTRAINT valid_evidence_type CHECK (evidence_type IN ('webpage', 'document', 'registry_entry', 'api_response', 'user_feedback', 'screenshot')),
    CONSTRAINT valid_collection_method CHECK (collection_method IN ('automated_crawl', 'api_fetch', 'manual_upload', 'registry_sync', 'scraper')),
    CONSTRAINT valid_confidence CHECK (confidence_level IN ('high', 'medium', 'low'))
);

-- Indexes for efficient querying
CREATE INDEX idx_evidence_firm_id ON evidence_collection(firm_id);
CREATE INDEX idx_evidence_type ON evidence_collection(evidence_type);
CREATE INDEX idx_evidence_hash ON evidence_collection(evidence_hash);
CREATE INDEX idx_evidence_collected_by ON evidence_collection(collected_by);
CREATE INDEX idx_evidence_metric ON evidence_collection(affects_metric);
CREATE INDEX idx_evidence_collected_at ON evidence_collection(collected_at DESC);
CREATE INDEX idx_evidence_verified ON evidence_collection(is_verified);
CREATE INDEX idx_evidence_stale ON evidence_collection(is_stale) WHERE is_stale = TRUE;

-- Composite indexes for audit queries
CREATE INDEX idx_evidence_firm_metric ON evidence_collection(firm_id, affects_metric);
CREATE INDEX idx_evidence_firm_collected ON evidence_collection(firm_id, collected_at DESC);

-- JSONB index for structured queries
CREATE INDEX idx_evidence_content_json ON evidence_collection USING GIN (content_json);

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_evidence_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for auto-updating updated_at
CREATE TRIGGER trigger_update_evidence_timestamp
    BEFORE UPDATE ON evidence_collection
    FOR EACH ROW
    EXECUTE FUNCTION update_evidence_timestamp();

-- Function to check if evidence is stale (older than 90 days)
CREATE OR REPLACE FUNCTION check_evidence_staleness()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.collected_at < NOW() - INTERVAL '90 days' THEN
        NEW.is_stale = TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for staleness check
CREATE TRIGGER trigger_check_evidence_staleness
    BEFORE INSERT OR UPDATE ON evidence_collection
    FOR EACH ROW
    EXECUTE FUNCTION check_evidence_staleness();

-- Sample data for testing
INSERT INTO evidence_collection (
    firm_id, evidence_type, evidence_source, evidence_hash,
    content_text, content_json, content_url,
    collected_by, collection_method,
    relevance_score, relevance_reason,
    affects_metric, affects_score_version, impact_weight,
    confidence_level, is_verified
) VALUES
    ('ftmocom', 'webpage', 'ftmo.com/about', 
     'a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd',
     'FTMO is regulated by CySEC license #273/15. Operating since 2015.',
     '{"license_number": "273/15", "regulator": "CySEC", "year_established": 2015}',
     'https://ftmo.com/about',
     'web_crawler', 'automated_crawl',
     0.95, 'Official regulatory information from firm website',
     'regulatory_compliance', 'v1.0', 0.85,
     'high', TRUE),
    
    ('fundedtradingplus', 'registry_entry', 'companies_house_uk',
     'b2c3d4e5f6789012345678901234567890123456789012345678901234abcde',
     'Company registered in UK, number 12345678, active status',
     '{"company_number": "12345678", "status": "active", "jurisdiction": "UK"}',
     'https://find-and-update.company-information.service.gov.uk',
     'RVI', 'registry_sync',
     1.0, 'Official government registry data',
     'jurisdiction_verification', 'v1.0', 1.0,
     'high', TRUE),
    
    ('topsteptrader', 'api_response', 'trustpilot_api',
     'c3d4e5f6789012345678901234567890123456789012345678901234abcdef0',
     NULL,
     '{"rating": 4.2, "review_count": 1250, "sentiment": "positive"}',
     'https://api.trustpilot.com/v1/business-units/topstep',
     'SSS', 'api_fetch',
     0.75, 'Third-party reputation signal',
     'soft_signals_sentiment', 'v1.0', 0.3,
     'medium', TRUE);

-- Comments
COMMENT ON TABLE evidence_collection IS 'Raw evidence supporting score calculations for audit trail and transparency';
COMMENT ON COLUMN evidence_collection.evidence_hash IS 'SHA-256 hash ensuring evidence integrity and detecting duplicates';
COMMENT ON COLUMN evidence_collection.content_json IS 'Structured data in JSONB format for efficient querying';
COMMENT ON COLUMN evidence_collection.impact_weight IS 'How much this evidence contributed to final score (0-1)';
COMMENT ON COLUMN evidence_collection.is_stale IS 'TRUE if evidence older than 90 days and needs refresh';
