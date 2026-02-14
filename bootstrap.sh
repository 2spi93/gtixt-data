#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/opt/gpti"
REPO_DIR="${ROOT_DIR}/gpti-data-bot"
INFRA_DIR="${REPO_DIR}/infra"

echo "[1/8] Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found. Install Docker Engine first."; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "ERROR: docker compose not available. Install Docker Compose plugin."; exit 1; }

echo "[2/8] Creating directories..."
mkdir -p "${ROOT_DIR}/data/seeds" "${ROOT_DIR}/data/raw" "${ROOT_DIR}/data/exports" "${ROOT_DIR}/docs"
mkdir -p "${REPO_DIR}/data/seeds" "${REPO_DIR}/data/raw" "${REPO_DIR}/data/exports"

echo "[3/8] Ensuring .env exists..."
if [ ! -f "${INFRA_DIR}/.env" ]; then
  cp "${INFRA_DIR}/.env.example" "${INFRA_DIR}/.env"
  echo "Created ${INFRA_DIR}/.env from example."
fi

echo "[4/8] Generating secrets (if needed)..."
if grep -q "CHANGE_ME_STRONG" "${INFRA_DIR}/.env"; then
  STRONG=$(openssl rand -hex 24 2>/dev/null || true)
  STRONG2=$(openssl rand -hex 24 2>/dev/null || true)
  ADMIN=$(openssl rand -hex 8 2>/dev/null || true)
  [ -z "${STRONG}" ] && STRONG="replace_me_$(date +%s)"
  [ -z "${STRONG2}" ] && STRONG2="replace_me_$(date +%s)"
  [ -z "${ADMIN}" ] && ADMIN="admin_$(date +%s)"
  sed -i "s/POSTGRES_PASSWORD=CHANGE_ME_STRONG/POSTGRES_PASSWORD=${STRONG}/" "${INFRA_DIR}/.env"
  sed -i "s/MINIO_ROOT_PASSWORD=CHANGE_ME_STRONG/MINIO_ROOT_PASSWORD=${STRONG2}/" "${INFRA_DIR}/.env"
  sed -i "s/MINIO_ROOT_USER=CHANGE_ME_ADMIN/MINIO_ROOT_USER=${ADMIN}/" "${INFRA_DIR}/.env"
  echo "Secrets generated."
fi

echo "[5/8] Starting docker compose stack..."
cd "${INFRA_DIR}"
docker compose up -d --build

echo "[6/8] Waiting for services (10s)..."
sleep 10

echo "[7/8] Creating MinIO buckets (gpti-raw, gpti-snapshots)..."
set +e
MINIO_USER=$(grep '^MINIO_ROOT_USER=' .env | cut -d= -f2-)
MINIO_PASS=$(grep '^MINIO_ROOT_PASSWORD=' .env | cut -d= -f2-)

NET_NAME="${INFRA_DIR##*/}_default"
docker run --rm --network "${NET_NAME}" minio/mc sh -lc "
  mc alias set local http://minio:9000 ${MINIO_USER} ${MINIO_PASS} >/dev/null 2>&1 &&
  mc mb -p local/gpti-raw >/dev/null 2>&1 || true &&
  mc mb -p local/gpti-snapshots >/dev/null 2>&1 || true
"
set -e

echo "[8/8] Done."
echo ""
echo "Prefect UI : http://YOUR_SERVER_IP:4200"
echo "MinIO Console: http://YOUR_SERVER_IP:9001"
echo ""
echo "Next:"
echo " - Put seed files into: ${REPO_DIR}/data/seeds/"
echo " - Then run: cd ${INFRA_DIR} && docker compose exec bot python -m gpti_bot discover"
