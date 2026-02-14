#!/usr/bin/env python3
import json
import psycopg2
import os

# Connexion PostgreSQL
conn = psycopg2.connect(
    host="localhost",
    database="gpti_bot",
    user="postgres",
    password="2e8c1b61927c490738c23e5e7976f69790a1b2bd4c75b1c8"
)
cur = conn.cursor()

# Charger seed.json
with open('/opt/gpti/gpti-data-bot/data/seeds/seed.json', 'r') as f:
    firms = json.load(f)

# Insérer chaque firme
count = 0
for firm in firms:
    cur.execute(
        "INSERT INTO firms (name, fca_reference, status) VALUES (%s, %s, %s)",
        (firm['firm_name'], firm.get('website', ''), firm.get('status', 'candidate'))
    )
    count += 1
    if count % 50 == 0:
        print(f"Chargé {count} firmes...")

conn.commit()
cur.close()
conn.close()

print(f"✅ {count} firmes chargées dans la base de données")
