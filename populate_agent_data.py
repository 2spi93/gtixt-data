#!/usr/bin/env python3
"""
Populate database with enriched firm data (simulating agent outputs).
This script will:
1. Load seed data
2. Populate firm_profiles with regulatory/compliance data
3. Populate snapshot_scores with actual scores
4. Populate evidence with supporting data
"""

import json
import sys
import os
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import execute_values

# Database connection with password from load_seed_data.py
try:
    conn = psycopg2.connect(
        host="localhost",
        database="gpti_bot",
        user="postgres",
        password="2e8c1b61927c490738c23e5e7976f69790a1b2bd4c75b1c8"
    )
    cur = conn.cursor()
    print("✅ Database connected")
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    sys.exit(1)

# Load seed data
try:
    with open('/opt/gpti/gpti-data-bot/data/seeds/seed.json', 'r') as f:
        firms = json.load(f)
    print(f"✅ Loaded {len(firms)} firms from seed.json")
except Exception as e:
    print(f"❌ Failed to load seed.json: {e}")
    conn.close()
    sys.exit(1)

# Get all firm IDs from database
try:
    cur.execute("SELECT firm_id, brand_name FROM firms ORDER BY firm_id")
    db_firms = {row[1]: row[0] for row in cur.fetchall()}
    print(f"✅ Found {len(db_firms)} firms in database")
except Exception as e:
    print(f"❌ Failed to fetch firms from database: {e}")
    conn.close()
    sys.exit(1)

# Populate firm_profiles with enriched data
profile_updates = []
for firm in firms:
    firm_name = firm.get('firm_name', '')
    firm_id = db_firms.get(firm_name)
    
    if not firm_id:
        continue
    
    profile_updates.append((
        firm_id,
        firm.get('firm_name', ''),
        'active',
        json.dumps(['FCA', 'UK CCA', 'Website']),  # data_sources
        '',  # verification_hash (will be computed later)
        'pending_review',  # audit_verdict
        'pending',  # oversight_gate_verdict
        datetime.now()  # last_updated
    ))

if profile_updates:
    try:
        execute_values(
            cur,
            """
            INSERT INTO firm_profiles 
            (firm_id, executive_summary, status_gtixt, data_sources, verification_hash, 
             audit_verdict, oversight_gate_verdict, last_updated)
            VALUES %s
            ON CONFLICT (firm_id) DO UPDATE SET
            status_gtixt = EXCLUDED.status_gtixt,
            last_updated = EXCLUDED.last_updated
            """,
            profile_updates,
            page_size=100
        )
        conn.commit()
        print(f"✅ Updated {len(profile_updates)} firm profiles")
    except Exception as e:
        print(f"❌ Failed to update firm_profiles: {e}")
        conn.rollback()

# Populate snapshot_scores with realistic test scores
snapshots = []
base_score_offset = 0

try:
    cur.execute("SELECT MAX(snapshot_id) FROM snapshot_scores")
    max_snapshot = cur.fetchone()[0]
    current_snapshot_id = (max_snapshot or 0) + 1
except:
    current_snapshot_id = 1

score_data = []
for i, (firm_name, firm_id) in enumerate(db_firms.items()):
    # Generate realistic scores
    import random
    random.seed(i)  # Consistent scores per firm
    
    base_score = 45 + random.randint(10, 45)  # 55-90 range
    pillar_scores = {
        "regulatory_compliance": base_score - random.randint(0, 15),
        "operational_resilience": base_score + random.randint(0, 10),
        "fair_dealing": base_score - random.randint(0, 10),
        "governance": base_score + random.randint(0, 5),
        "market_integrity": base_score - random.randint(5, 15),
    }
    
    metric_scores = {
        "rvi": 50 + random.randint(10, 40),
        "sss": 45 + random.randint(15, 35),
        "rem": 55 + random.randint(10, 30),
        "irs": 48 + random.randint(15, 37),
        "frp": 52 + random.randint(12, 33),
        "mis": 50 + random.randint(10, 35),
    }
    
    score_data.append((
        current_snapshot_id,
        firm_id,
        base_score,
        json.dumps(pillar_scores),
        json.dumps(metric_scores),
        random.randint(5, 20),  # NA rate
        0.85 + random.random() * 0.15,  # confidence
    ))

if score_data:
    try:
        execute_values(
            cur,
            """
            INSERT INTO snapshot_scores 
            (snapshot_id, firm_id, score_0_100, pillar_scores, metric_scores, na_rate, confidence)
            VALUES %s
            ON CONFLICT (snapshot_id, firm_id) DO UPDATE SET
            score_0_100 = EXCLUDED.score_0_100,
            pillar_scores = EXCLUDED.pillar_scores,
            metric_scores = EXCLUDED.metric_scores,
            updated_at = NOW()
            """,
            score_data,
            page_size=100
        )
        conn.commit()
        print(f"✅ Populated {len(score_data)} snapshot_scores")
    except Exception as e:
        print(f"❌ Failed to populate snapshot_scores: {e}")
        conn.rollback()

# Populate evidence with sample data
evidence_data = []
for firm_name, firm_id in list(db_firms.items())[:50]:  # First 50 firms
    evidence_data.append((
        firm_id,
        'fca_reference_number',
        'https://register.fca.org.uk',
        f"{firm_id}_fca_ref",  # SHA256 placeholder
        json.dumps({
            "source": "FCA Register",
            "status": "authorized",
            "permissions": ["CASS", "MiFID II"]
        }),
        '',  # raw_object_path
        datetime.now()
    ))

if evidence_data:
    try:
        execute_values(
            cur,
            """
            INSERT INTO evidence 
            (firm_id, key, source_url, sha256, excerpt, raw_object_path, created_at)
            VALUES %s
            ON CONFLICT (firm_id, key, sha256) DO NOTHING
            """,
            evidence_data,
            page_size=100
        )
        conn.commit()
        print(f"✅ Populated {len(evidence_data)} evidence records")
    except Exception as e:
        print(f"❌ Failed to populate evidence: {e}")
        conn.rollback()

cur.close()
conn.close()

print("\n🎉 Agent data population complete!")
print(f"   - snapshot_id: {current_snapshot_id}")
print(f"   - Total firms scored: {len(score_data)}")
print(f"   - Total evidence records: {len(evidence_data)}")
