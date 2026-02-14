-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Table for tracking external ground-truth events
-- Used to validate if our scoring captures operational risks
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firm_id VARCHAR(255),
    firm_name VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    -- event_type: 'payout_controversy', 'regulatory_action', 'site_down', 'policy_change', 'other'
    description TEXT,
    event_date TIMESTAMP WITH TIME ZONE NOT NULL,
    severity VARCHAR(20), -- 'critical', 'high', 'medium', 'low'
    source_url VARCHAR(500),
    source_title VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    recorded_by VARCHAR(255), -- who reported this (email or system)
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_firm_date ON events (firm_id, event_date);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);

-- Table for storing validation metrics snapshots
-- Run every validation cycle to track 6 tests
CREATE TABLE IF NOT EXISTS validation_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id VARCHAR(255) NOT NULL UNIQUE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Test 1: Coverage & Data Sufficiency
    total_firms INTEGER,
    firms_with_rules_extracted INTEGER,
    firms_with_pricing_extracted INTEGER,
    coverage_percent DECIMAL(5,2),
    avg_na_rate DECIMAL(5,2),
    agent_c_pass_rate DECIMAL(5,2),
    
    -- Test 2: Stability / Turnover
    prev_snapshot_id VARCHAR(255),
    avg_score_change DECIMAL(8,4),
    top_10_turnover INTEGER,
    top_20_turnover INTEGER,
    verdict_churn_rate DECIMAL(5,2),
    
    -- Test 3: Sensitivity / Stress tests
    pillar_sensitivity_mean DECIMAL(8,4), -- avg impact of removing pillar
    fallback_usage_percent DECIMAL(5,2), -- % of scores using fallback values
    stability_score DECIMAL(5,2), -- 0-100: how robust is the model
    
    -- Test 4: Ground-truth events
    events_in_period INTEGER, -- events that occurred before/after this snapshot
    events_predicted INTEGER, -- events our model flagged before they happened
    prediction_precision DECIMAL(5,2),
    
    -- Test 5: Calibration / Bias checks
    score_distribution_skew DECIMAL(8,4),
    jurisdiction_bias_score DECIMAL(5,2),
    model_type_bias_score DECIMAL(5,2),
    
    -- Test 6: Auditability
    evidence_linkage_rate DECIMAL(5,2), -- % of scores with traceable URLs
    version_metadata VARCHAR(255),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_metrics_snapshot ON validation_metrics (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_validation_metrics_timestamp ON validation_metrics (timestamp);

-- Table for tracking alerts/anomalies
CREATE TABLE IF NOT EXISTS validation_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(100) NOT NULL,
    -- alert_type: 'na_spike', 'coverage_drop', 'turnover_spike', 'bias_detected', 'fail_rate_up'
    severity VARCHAR(20), -- 'critical', 'warning', 'info'
    metric_name VARCHAR(100),
    current_value DECIMAL(8,4),
    threshold_value DECIMAL(8,4),
    message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_validation_alerts_snapshot_type ON validation_alerts (snapshot_id, alert_type);
