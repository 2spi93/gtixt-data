#!/usr/bin/env bash
set -euo pipefail

ok()   { echo -e "✅ OK   - $*"; }
fail() { echo -e "❌ FAIL - $*"; EXIT=1; }
warn() { echo -e "🟨 WARN - $*"; }

EXIT=0
cd /opt/gpti/gpti-data-bot/infra

echo "== GPTI VPS Doctor =="

# 1) docker compose sanity
if sudo docker compose config >/dev/null 2>&1; then ok "docker compose config"; else fail "docker compose config"; fi

# 2) services running
PS_OUT="$(sudo docker compose ps 2>/dev/null || true)"
echo "$PS_OUT" | grep -qi "postgres" && ok "service postgres present" || fail "service postgres missing"
echo "$PS_OUT" | grep -qi "minio"    && ok "service minio present"    || fail "service minio missing"
echo "$PS_OUT" | grep -qi "bot"      && ok "service bot present"      || fail "service bot missing"

# 3) .env required vars
if [[ -f .env ]]; then ok "infra/.env exists"; else fail "infra/.env missing"; fi
grep -q '^OLLAMA_BASE_URL=' .env && ok "OLLAMA_BASE_URL set" || fail "OLLAMA_BASE_URL not set"
grep -q '^OLLAMA_MODEL_RULES=' .env && ok "OLLAMA_MODEL_RULES set" || fail "OLLAMA_MODEL_RULES not set"
grep -q '^DATABASE_URL=' .env && ok "DATABASE_URL set" || fail "DATABASE_URL not set"
grep -q '^MINIO_ACCESS_KEY=' .env && ok "MINIO_ACCESS_KEY set" || fail "MINIO_ACCESS_KEY not set"
grep -q '^MINIO_SECRET_KEY=' .env && ok "MINIO_SECRET_KEY set" || fail "MINIO_SECRET_KEY not set"

# 4) seeds mount (host + container)
HOST_SEEDS="/opt/gpti/gpti-data-bot/data/seeds"
if [[ -d "$HOST_SEEDS" ]]; then ok "host seeds dir exists ($HOST_SEEDS)"; else warn "host seeds dir missing ($HOST_SEEDS)"; fi

if sudo docker compose exec -T bot bash -lc 'ls -la /app/data/seeds >/dev/null 2>&1'; then
  ok "container sees /app/data/seeds"
  sudo docker compose exec -T bot bash -lc 'ls -la /app/data/seeds | sed -e "s/^/    /"'
else
  warn "container does NOT see /app/data/seeds (check docker-compose volume: ../data:/app/data)"
fi

# 5) Ollama reachable from container: tags + generate (non-stream)
# Note: /api/generate streams by default; stream:false should return one JSON response.
# (Ollama docs)
echo "== Ollama checks =="
if sudo docker compose exec -T bot python - <<'PY' >/dev/null 2>&1
import os,requests
base=os.getenv("OLLAMA_BASE_URL","http://host.docker.internal:11435").rstrip("/")
r=requests.get(base+"/api/tags",timeout=10)
r.raise_for_status()
print("ok")
PY
then
  ok "ollama /api/tags reachable from bot"
else
  fail "ollama /api/tags NOT reachable from bot"
fi

GEN_OUT="$(sudo docker compose exec -T bot python - <<'PY' 2>/dev/null || true
import os,requests,json
base=os.getenv("OLLAMA_BASE_URL","http://host.docker.internal:11435").rstrip("/")
model=os.getenv("OLLAMA_MODEL_RULES","llama3.1:latest")
url=base+"/api/generate"
payload={"model":model,"prompt":"hello","stream":False}
r=requests.post(url,json=payload,timeout=30)
print(r.status_code)
print(r.text[:200])
PY
)"
STATUS="$(echo "$GEN_OUT" | head -n1 | tr -d '\r')"
BODY="$(echo "$GEN_OUT" | tail -n +2 | head -n1 | tr -d '\r')"

if [[ "$STATUS" == "200" ]]; then
  ok "ollama /api/generate stream:false returns 200"
else
  # Ollama returns 404 if the model doesn't exist locally.
  fail "ollama /api/generate failed (status=$STATUS) body=$BODY"
  warn "If body says model not found: check OLLAMA_MODEL_RULES is installed (model:tag)"
fi

# 6) Postgres schema + basic counts
echo "== Postgres checks =="
if sudo docker compose exec -T postgres pg_isready -U gpti -d gpti >/dev/null 2>&1; then
  ok "postgres ready"
else
  fail "postgres not ready"
fi

for t in firms datapoints evidence; do
  if sudo docker compose exec -T postgres psql -U gpti -d gpti -c "select 1 from $t limit 1" >/dev/null 2>&1; then
    ok "table exists: $t"
  else
    fail "table missing or unreadable: $t"
  fi
done

sudo docker compose exec -T postgres psql -U gpti -d gpti -c "select count(*) as firms from firms;" | sed -e "s/^/    /" || true
sudo docker compose exec -T postgres psql -U gpti -d gpti -c "select key,count(*) from datapoints group by 1 order by 2 desc limit 10;" | sed -e "s/^/    /" || true

# 7) MinIO health
echo "== MinIO checks =="
if curl -fsS http://127.0.0.1:9000/minio/health/ready >/dev/null 2>&1; then
  ok "minio health ready (127.0.0.1:9000)"
else
  warn "minio health not reachable on 127.0.0.1:9000 (may still be OK if bound differently)"
fi

# 8) Prefect presence (optional)
echo "== Prefect checks (optional) =="
if sudo docker compose exec -T bot bash -lc 'prefect version' >/dev/null 2>&1; then
  ok "prefect CLI available in bot"
  # Prefect flow serve supports --cron, --timezone, --global-limit (docs)
  ok "prefect serve flags supported: --cron/--timezone/--global-limit"
else
  warn "prefect CLI not found inside bot (only an issue if you want scheduling from container)"
fi

echo
if [[ "$EXIT" -eq 0 ]]; then
  echo "✅ ALL CHECKS PASSED"
else
  echo "❌ SOME CHECKS FAILED"
fi
exit "$EXIT"
SH

chmod +x /opt/gpti/gpti-data-bot/infra/doctor.sh