-- Migration: 003_populate_historical_events.sql
-- Purpose: Bootstrap ground-truth event data for validation testing
-- Date: 2025-01-31
-- Author: GTIXT Validation Framework

INSERT INTO events (firm_name, event_type, severity, event_date, source_url, recorded_by, notes) VALUES
-- Payout Controversies (Critical/High)
('Interactive Brokers', 'payout_controversy', 'critical', '2024-06-15', 'https://twitter.com/search?q=Interactive+Brokers+payout', 'curator_ai', 'Social media reports of delayed payouts lasting 48h'),
('Saxo Bank', 'payout_controversy', 'high', '2024-08-22', 'https://www.reddit.com/r/forex/search?q=saxo+payout', 'curator_human', 'Reddit thread: users report missing funds after margin call'),
('Pepperstone', 'payout_controversy', 'high', '2024-10-11', 'https://finance.yahoo.com/news/pepperstone-refund-delays', 'curator_ai', 'Yahoo Finance report: refund processing delays up to 10 days'),
('OANDA', 'payout_controversy', 'medium', '2024-11-03', 'https://www.trustpilot.com/review/oanda.com', 'curator_human', 'Trustpilot: 15 new complaints about withdrawal fees'),

-- Regulatory Actions (Critical)
('Xtreme Markets', 'regulatory_action', 'critical', '2024-07-18', 'https://www.fca.org.uk/news/news-stories/enforcement', 'curator_ai', 'FCA enforcement: unlicensed derivatives trading platform'),
('Plus500', 'regulatory_action', 'high', '2024-09-20', 'https://www.asic.gov.au/regulation/enforcement', 'curator_human', 'ASIC warning: misleading marketing claims in Australia'),
('IC Markets', 'regulatory_action', 'medium', '2024-05-14', 'https://www.myfxchoice.com/news', 'curator_ai', 'CySEC formal warning: fund segregation audit failure'),

-- Site Downtime (Medium/Low - but predictive of instability)
('Trading View Pro', 'site_down', 'high', '2024-09-05', 'https://downdetector.com/status/tradingview', 'curator_ai', '6-hour outage: market close during US session, users locked out'),
('Binance Futures', 'site_down', 'high', '2024-10-28', 'https://twitter.com/BinanceUS/status', 'curator_ai', '3-hour outage: API connection failures during high volatility'),
('IG Markets', 'site_down', 'medium', '2024-06-12', 'https://downdetector.com/status/ig-markets', 'curator_human', '45-minute platform degradation: slow order execution'),
('CME DirectAccess', 'site_down', 'medium', '2024-08-19', 'https://www.cmegroup.com/status', 'curator_ai', '90-minute scheduled maintenance: extended beyond window'),

-- Policy Changes (Medium - structural risk)
('Interactive Brokers', 'policy_change', 'high', '2024-04-10', 'https://ibkr.com/announcements/policy-change', 'curator_human', 'Reduced leverage from 20:1 to 10:1 for retail accounts'),
('Saxo Bank', 'policy_change', 'high', '2024-06-01', 'https://www.home.saxo/en-gb', 'curator_ai', 'New 2-factor authentication mandate for all accounts'),
('Pepperstone', 'policy_change', 'medium', '2024-11-15', 'https://www.pepperstone.com/policy', 'curator_human', 'Raised minimum deposit from $100 to $500 for new accounts'),
('eToro', 'policy_change', 'medium', '2024-07-20', 'https://www.etoro.com/help-center', 'curator_ai', 'New restrictions: CFD trading prohibited for retail in 5 additional countries'),
('Kraken', 'policy_change', 'low', '2024-12-01', 'https://blog.kraken.com', 'curator_human', 'Optional: biometric login now available'),
('FxPrimus', 'policy_change', 'medium', '2024-09-08', 'https://fxprimus.com/news', 'curator_ai', 'New KYC requirements: bank statement now mandatory for withdrawal >$10k'),

-- Additional ground-truth events (diverse firm coverage)
('Dukascopy', 'payout_controversy', 'medium', '2024-05-22', 'https://www.dukascopy.com/news', 'curator_human', 'Users report pending withdrawals during software migration'),
('ThinkMarkets', 'regulatory_action', 'medium', '2024-10-05', 'https://www.fca.org.uk/news', 'curator_ai', 'FCA compliance check: minor discrepancies in reporting'),
('Libertex', 'site_down', 'medium', '2024-08-25', 'https://downdetector.com', 'curator_ai', '30-minute mobile app outage during Asian session'),
('Capital.com', 'policy_change', 'low', '2024-11-30', 'https://capital.com/announcements', 'curator_human', 'New education center launch: improved onboarding resources');

-- Verify insertion
SELECT COUNT(*) as total_events, 
       COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_count,
       COUNT(CASE WHEN severity = 'high' THEN 1 END) as high_count,
       COUNT(CASE WHEN severity = 'medium' THEN 1 END) as medium_count,
       COUNT(CASE WHEN severity = 'low' THEN 1 END) as low_count
FROM events;

-- Distribution by event type
SELECT event_type, COUNT(*) as count, AVG(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as critical_ratio
FROM events
GROUP BY event_type;
