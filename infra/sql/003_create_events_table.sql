-- Migration: 003_create_events_table.sql
-- Purpose: Ground-truth event tracking for validation framework
-- Created: 2026-02-01
-- Phase: 1 (Validation Framework)

-- Events table stores curated ground-truth events for validation
CREATE TABLE IF NOT EXISTS ground_truth_events (
    event_id SERIAL PRIMARY KEY,
    firm_id VARCHAR(50) NOT NULL,
    event_date DATE NOT NULL,
    event_type VARCHAR(50) NOT NULL, -- 'regulatory_action', 'closure', 'payout_change', 'rule_change', 'scam_report'
    event_severity VARCHAR(20) NOT NULL, -- 'critical', 'high', 'medium', 'low'
    event_description TEXT NOT NULL,
    
    -- Source tracking
    source_type VARCHAR(50) NOT NULL, -- 'regulator', 'news', 'user_report', 'curator'
    source_url TEXT,
    source_reliability VARCHAR(20) NOT NULL, -- 'verified', 'high', 'medium', 'low'
    
    -- Expected impact
    expected_score_impact INTEGER, -- Expected change in score (-100 to +100)
    expected_direction VARCHAR(10), -- 'decrease', 'increase', 'neutral'
    
    -- Validation tracking
    validated_by VARCHAR(100), -- curator username/email
    validated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    validation_notes TEXT,
    
    -- Verification status
    is_verified BOOLEAN DEFAULT FALSE,
    verification_count INTEGER DEFAULT 0,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_severity CHECK (event_severity IN ('critical', 'high', 'medium', 'low')),
    CONSTRAINT valid_reliability CHECK (source_reliability IN ('verified', 'high', 'medium', 'low')),
    CONSTRAINT valid_direction CHECK (expected_direction IN ('decrease', 'increase', 'neutral'))
);

-- Indexes for common queries
CREATE INDEX idx_events_firm_id ON ground_truth_events(firm_id);
CREATE INDEX idx_events_date ON ground_truth_events(event_date DESC);
CREATE INDEX idx_events_type ON ground_truth_events(event_type);
CREATE INDEX idx_events_severity ON ground_truth_events(event_severity);
CREATE INDEX idx_events_verified ON ground_truth_events(is_verified);
CREATE INDEX idx_events_created ON ground_truth_events(created_at DESC);

-- Composite index for validation queries
CREATE INDEX idx_events_firm_date ON ground_truth_events(firm_id, event_date DESC);

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_events_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for auto-updating updated_at
CREATE TRIGGER trigger_update_events_timestamp
    BEFORE UPDATE ON ground_truth_events
    FOR EACH ROW
    EXECUTE FUNCTION update_events_timestamp();

-- Sample data for testing
INSERT INTO ground_truth_events (
    firm_id, event_date, event_type, event_severity, event_description,
    source_type, source_url, source_reliability,
    expected_score_impact, expected_direction,
    validated_by, validation_notes, is_verified
) VALUES
    ('ftmocom', '2025-12-15', 'regulatory_action', 'high', 
     'CySEC issued warning regarding unauthorized operations in EU jurisdiction',
     'regulator', 'https://cysec.gov.cy/warnings/ftmo-warning-2025', 'verified',
     -15, 'decrease',
     'curator@gpti.org', 'Official CySEC warning, verified source', TRUE),
    
    ('fundedtradingplus', '2025-11-20', 'payout_change', 'medium',
     'Increased payout threshold from $10k to $25k without prior notice',
     'user_report', NULL, 'medium',
     -8, 'decrease',
     'curator@gpti.org', 'Multiple user reports confirmed', TRUE),
    
    ('topsteptrader', '2025-10-05', 'rule_change', 'low',
     'Introduced new transparency dashboard for trader performance',
     'news', 'https://example.com/topstep-transparency', 'high',
     5, 'increase',
     'curator@gpti.org', 'Positive development for transparency', TRUE);

-- Comments
COMMENT ON TABLE ground_truth_events IS 'Curated ground-truth events for validating score changes';
COMMENT ON COLUMN ground_truth_events.event_severity IS 'Impact level: critical (regulatory shutdown), high (major violation), medium (policy change), low (minor update)';
COMMENT ON COLUMN ground_truth_events.source_reliability IS 'Source trustworthiness: verified (official regulator), high (major news), medium (user reports), low (unconfirmed)';
COMMENT ON COLUMN ground_truth_events.expected_score_impact IS 'Expected change in score: negative values decrease score, positive increase';
