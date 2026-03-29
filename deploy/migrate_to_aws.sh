#!/usr/bin/env bash
# Migrates Postgres + Qdrant data from Hetzner VPS to AWS EC2.
#
# Run this from your laptop — it can SSH into both servers.
# Data flows: Hetzner → your laptop (pipe) → AWS. No intermediate files for Postgres.
# Qdrant snapshot is staged locally then pushed to AWS.
#
# Usage:
#   ./deploy/migrate_to_aws.sh
#
# Required env vars:
#   HETZNER_HOST         — Hetzner server IP or hostname
#   AWS_HOST             — AWS EC2 IP or hostname
#
# Optional env vars (defaults shown):
#   HETZNER_USER         — deploy
#   HETZNER_DIR          — ~/projects/mm-forums-vector-db
#   AWS_USER             — ec2-user
#   AWS_DIR              — ~/projects/mm-forums-vector-db
#   POSTGRES_USER        — mm
#   POSTGRES_DB          — mm_forum
#   QDRANT_COLLECTION    — mm_forum_posts
#   SNAPSHOT_DIR         — /tmp/mm-forums-migration

set -euo pipefail

: "${HETZNER_HOST:?HETZNER_HOST is required}"
: "${AWS_HOST:?AWS_HOST is required}"

HETZNER_USER="${HETZNER_USER:-deploy}"
HETZNER_DIR="${HETZNER_DIR:-~/projects/mm-forums-vector-db}"
AWS_USER="${AWS_USER:-ec2-user}"
AWS_DIR="${AWS_DIR:-~/projects/mm-forums-vector-db}"
POSTGRES_USER="${POSTGRES_USER:-mm}"
POSTGRES_DB="${POSTGRES_DB:-mm_forum}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-mm_forum_posts}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-/tmp/mm-forums-migration}"

HETZNER="ssh -T ${HETZNER_USER}@${HETZNER_HOST}"
AWS="ssh -T ${AWS_USER}@${AWS_HOST}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

echo ""
echo "========================================================"
echo "  mm-forums Hetzner → AWS migration"
echo "  Hetzner: ${HETZNER_USER}@${HETZNER_HOST}:${HETZNER_DIR}"
echo "  AWS:     ${AWS_USER}@${AWS_HOST}:${AWS_DIR}"
echo "========================================================"
echo ""
echo "This will OVERWRITE data on the AWS instance."
read -rp "Continue? [y/N] " confirm
[[ "${confirm}" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

mkdir -p "${SNAPSHOT_DIR}"

# ── Step 1: Postgres ────────────────────────────────────────────────────────

echo ""
echo "==> [1/4] Streaming Postgres: Hetzner → AWS..."

# Pipe pg_dump (custom format) from Hetzner through local into pg_restore on AWS.
# -T disables TTY allocation so binary data flows cleanly through the pipe.
ssh -T "${HETZNER_USER}@${HETZNER_HOST}" \
  "cd ${HETZNER_DIR} && ${COMPOSE} exec -T postgres \
    pg_dump -U ${POSTGRES_USER} --format=custom ${POSTGRES_DB}" \
| ssh -T "${AWS_USER}@${AWS_HOST}" \
  "cd ${AWS_DIR} && ${COMPOSE} exec -T postgres \
    pg_restore -U ${POSTGRES_USER} --dbname=${POSTGRES_DB} \
    --clean --if-exists --no-owner --no-privileges -v" \
  2>&1 | grep -v "^pg_restore: warning" || true

echo "    Postgres done."

# ── Step 2: Qdrant snapshot ─────────────────────────────────────────────────

echo ""
echo "==> [2/4] Creating Qdrant snapshot on Hetzner..."

SNAPSHOT_NAME=$(${HETZNER} "cd ${HETZNER_DIR} && \
  ${COMPOSE} exec -T qdrant \
    wget -qO- --post-data='' \
    'http://localhost:6333/collections/${QDRANT_COLLECTION}/snapshots' \
  | python3 -c \"import sys,json; print(json.load(sys.stdin)['result']['name'])\"")

echo "    Snapshot: ${SNAPSHOT_NAME}"

# ── Step 3: Download snapshot from Hetzner ──────────────────────────────────

echo ""
echo "==> [3/4] Downloading snapshot to local ${SNAPSHOT_DIR}..."

# Copy out of the Qdrant container to the host, then SCP to local
${HETZNER} "cd ${HETZNER_DIR} && \
  ${COMPOSE} exec -T qdrant \
    sh -c 'cat /qdrant/storage/snapshots/${QDRANT_COLLECTION}/${SNAPSHOT_NAME}'" \
> "${SNAPSHOT_DIR}/${SNAPSHOT_NAME}"

echo "    Downloaded: ${SNAPSHOT_DIR}/${SNAPSHOT_NAME} ($(du -sh "${SNAPSHOT_DIR}/${SNAPSHOT_NAME}" | cut -f1))"

# ── Step 4: Upload and restore snapshot on AWS ───────────────────────────────

echo ""
echo "==> [4/4] Uploading and restoring Qdrant snapshot on AWS..."

# Stream snapshot into the AWS Qdrant container
cat "${SNAPSHOT_DIR}/${SNAPSHOT_NAME}" \
| ssh -T "${AWS_USER}@${AWS_HOST}" \
  "cd ${AWS_DIR} && \
  ${COMPOSE} exec -T qdrant \
    sh -c 'cat > /tmp/${SNAPSHOT_NAME}' && \
  ${COMPOSE} exec -T qdrant \
    wget -qO- \
    --method=POST \
    --body-file=/tmp/${SNAPSHOT_NAME} \
    --header='Content-Type: multipart/form-data' \
    'http://localhost:6333/collections/${QDRANT_COLLECTION}/snapshots/upload?priority=snapshot'"

echo "    Qdrant restore done."

# ── Summary ─────────────────────────────────────────────────────────────────

echo ""
echo "========================================================"
echo "  Migration complete."
echo ""
echo "  Before flipping DNS, verify on AWS:"
echo "    1. App loads:  https://<aws-domain>"
echo "    2. Search returns results"
echo "    3. Stats show expected topic/post/embedding counts"
echo ""
echo "  Then:"
echo "    4. Update DNS A record to AWS IP"
echo "    5. Wait for TTL to expire"
echo "    6. Shut down Hetzner server"
echo "========================================================"
